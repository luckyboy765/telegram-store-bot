"""Handler sisi pembeli: menu, katalog, detail produk, alur beli QRIS."""
from __future__ import annotations

import asyncio
import logging
import uuid

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
from config import INVOICE_EXPIRE_MINUTES, STORE_NAME, is_admin
from delivery import fulfill_order
from payments import provider

router = Router()
log = logging.getLogger(__name__)

# order_id -> asyncio.Task poller, biar tidak dobel.
_pollers: dict[int, asyncio.Task] = {}


def _welcome(name: str) -> str:
    return (
        f"👋 Halo <b>{name}</b>!\n\n"
        f"Selamat datang di <b>{STORE_NAME}</b> 🛒\n"
        f"Pilih menu di bawah untuk mulai belanja."
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    u = message.from_user
    await db.upsert_user(u.id, u.username, u.first_name)
    await message.answer(
        _welcome(u.first_name), reply_markup=kb.main_menu(is_admin(u.id))
    )


@router.callback_query(F.data == "home")
async def cb_home(call: CallbackQuery) -> None:
    await call.message.edit_text(
        _welcome(call.from_user.first_name),
        reply_markup=kb.main_menu(is_admin(call.from_user.id)),
    )
    await call.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery) -> None:
    await call.answer()


@router.callback_query(F.data.startswith("catalog:"))
async def cb_catalog(call: CallbackQuery) -> None:
    page = int(call.data.split(":")[1])
    products = await db.list_products(active_only=True)
    if not products:
        await call.answer("Belum ada produk 😅", show_alert=True)
        return
    await call.message.edit_text(
        f"🛍️ <b>KATALOG PRODUK</b>\nPilih produk sesuai stok tersedia 👇",
        reply_markup=kb.catalog_kb(products, page),
    )
    await call.answer()


@router.callback_query(F.data.startswith("prod:"))
async def cb_product(call: CallbackQuery) -> None:
    _, pid, page = call.data.split(":")
    product = await db.get_product(int(pid))
    if not product:
        await call.answer("Produk tidak ditemukan.", show_alert=True)
        return
    stok = "❌ Habis" if product["available"] <= 0 else f"✅ {product['available']}"
    text = (
        f"{product['emoji']} <b>{product['name']}</b>\n"
        f"{'─' * 22}\n"
        f"{product['description'] or '(tanpa deskripsi)'}\n\n"
        f"💵 Harga: <b>Rp {product['price']:,}</b>\n"
        f"📦 Stok: {stok}"
    )
    await call.message.edit_text(text, reply_markup=kb.product_kb(product, int(page)))
    await call.answer()


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(call: CallbackQuery, bot: Bot) -> None:
    pid = int(call.data.split(":")[1])
    product = await db.get_product(pid)
    if not product or product["available"] <= 0:
        await call.answer("Maaf, stok habis 😔", show_alert=True)
        return

    await call.answer("Membuat invoice… ⏳")
    try:
        invoice = await provider.create_invoice(
            order_ref=f"ORD-{call.from_user.id}-{uuid.uuid4().hex[:8]}",
            amount=product["price"],
            product_name=product["name"],
            customer=call.from_user.first_name,
        )
    except Exception as e:
        log.exception("Gagal buat invoice")
        await call.message.answer(f"❌ Gagal membuat invoice: {e}")
        return

    order_id = await db.create_order(
        call.from_user.id, product, invoice.amount,
        invoice.reference, invoice.pay_url, invoice.qr_url or "",
    )

    caption = (
        f"🧾 <b>INVOICE #{order_id}</b>\n"
        f"{'─' * 22}\n"
        f"{product['emoji']} {product['name']}\n"
        f"💵 Total: <b>Rp {invoice.amount:,}</b>\n"
        f"⏱️ Berlaku {INVOICE_EXPIRE_MINUTES} menit\n\n"
        f"Scan QRIS di bawah / buka halaman bayar.\n"
        f"Status akan ke-update <b>otomatis</b> setelah kamu bayar."
    )
    markup = kb.invoice_kb(order_id, invoice.pay_url)
    if invoice.qr_url and invoice.qr_url.startswith("http"):
        await call.message.answer_photo(invoice.qr_url, caption=caption, reply_markup=markup)
    else:
        # qr_url berupa string QRIS mentah (bukan gambar) atau kosong
        extra = f"\n\n<code>{invoice.qr_url}</code>" if invoice.qr_url else ""
        await call.message.answer(caption + extra, reply_markup=markup)

    # Mulai auto-poll status.
    _pollers[order_id] = asyncio.create_task(_poll_order(bot, order_id, invoice.reference))


async def _poll_order(bot: Bot, order_id: int, reference: str) -> None:
    """Cek status ke gateway berkala sampai lunas / kedaluwarsa.

    Ini jalur cadangan supaya bot tetap otomatis walau webhook tidak dipakai.
    Kalau webhook aktif, fulfill_order sudah idempoten jadi aman dobel."""
    deadline = asyncio.get_event_loop().time() + INVOICE_EXPIRE_MINUTES * 60
    try:
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(6)
            order = await db.get_order(order_id)
            if not order or order["status"] != "pending":
                return  # sudah diproses (mis. lewat webhook) atau dibatalkan
            status = await provider.check_status(reference)
            if status == "PAID":
                await fulfill_order(bot, order_id)
                return
            if status in ("EXPIRED", "FAILED"):
                await db.set_order_status(order_id, "expired")
                await bot.send_message(order["user_id"],
                                       f"⛔ Invoice #{order_id} kedaluwarsa/gagal.")
                return
        # timeout
        order = await db.get_order(order_id)
        if order and order["status"] == "pending":
            await db.set_order_status(order_id, "expired")
    finally:
        _pollers.pop(order_id, None)


@router.callback_query(F.data.startswith("check:"))
async def cb_check(call: CallbackQuery, bot: Bot) -> None:
    order_id = int(call.data.split(":")[1])
    order = await db.get_order(order_id)
    if not order:
        await call.answer("Order tidak ditemukan.", show_alert=True)
        return
    if order["status"] in ("paid", "delivered"):
        await call.answer("✅ Sudah lunas!", show_alert=True)
        return
    status = await provider.check_status(order["reference"])
    if status == "PAID":
        await fulfill_order(bot, order_id)
        await call.answer("✅ Pembayaran terkonfirmasi!", show_alert=True)
    else:
        await call.answer("⏳ Belum ada pembayaran masuk.", show_alert=True)


@router.callback_query(F.data.startswith("cancel:"))
async def cb_cancel(call: CallbackQuery) -> None:
    order_id = int(call.data.split(":")[1])
    order = await db.get_order(order_id)
    if order and order["status"] == "pending":
        await db.set_order_status(order_id, "failed")
        task = _pollers.pop(order_id, None)
        if task:
            task.cancel()
        await call.message.edit_reply_markup(reply_markup=None)
        await call.answer("Invoice dibatalkan.")
    else:
        await call.answer("Tidak bisa dibatalkan.", show_alert=True)


@router.callback_query(F.data == "myorders")
async def cb_myorders(call: CallbackQuery) -> None:
    orders = []
    all_ids = None  # tidak perlu; query langsung
    # Query sederhana lewat helper get_order tidak cocok; pakai list bawaan.
    import aiosqlite
    from config import DB_PATH
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = db._row_to_dict
        cur = await conn.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10",
            (call.from_user.id,),
        )
        orders = await cur.fetchall()

    if not orders:
        await call.answer("Belum ada pesanan.", show_alert=True)
        return

    emoji = {"pending": "⏳", "paid": "💰", "delivered": "✅",
             "expired": "⛔", "failed": "❌"}
    lines = ["🧾 <b>10 Pesanan Terakhir</b>\n"]
    for o in orders:
        lines.append(
            f"{emoji.get(o['status'], '•')} #{o['id']} — {o['product_name']} "
            f"(Rp {o['amount']:,}) — {o['status']}"
        )
    await call.message.edit_text("\n".join(lines), reply_markup=kb.back_home())
    await call.answer()

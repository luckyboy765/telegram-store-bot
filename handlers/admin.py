"""Panel admin: kelola produk, stok, lihat statistik, broadcast."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
from config import is_admin

router = Router()
log = logging.getLogger(__name__)


# Semua handler di router ini hanya untuk admin.
@router.message.middleware
async def _only_admin_msg(handler, event: Message, data):
    if not is_admin(event.from_user.id):
        return
    return await handler(event, data)


@router.callback_query.middleware
async def _only_admin_cb(handler, event: CallbackQuery, data):
    if not is_admin(event.from_user.id):
        await event.answer("Khusus admin.", show_alert=True)
        return
    return await handler(event, data)


class AddProduct(StatesGroup):
    name = State()
    desc = State()
    emoji = State()
    price = State()
    ptype = State()
    stock = State()


class AddStock(StatesGroup):
    items = State()


class Broadcast(StatesGroup):
    text = State()


def _admin_home_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Tambah Produk", callback_data="admin:add")
    kb.button(text="📦 Kelola Produk", callback_data="admin:list")
    kb.button(text="📊 Statistik", callback_data="admin:stats")
    kb.button(text="📢 Broadcast", callback_data="admin:bc")
    kb.button(text="🏠 Menu Utama", callback_data="home")
    kb.adjust(1)
    return kb.as_markup()


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    await message.answer("⚙️ <b>Panel Admin</b>", reply_markup=_admin_home_kb())


@router.callback_query(F.data == "admin:home")
async def cb_admin_home(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text("⚙️ <b>Panel Admin</b>", reply_markup=_admin_home_kb())
    await call.answer()


# ---------------- Statistik ----------------
@router.callback_query(F.data == "admin:stats")
async def cb_stats(call: CallbackQuery) -> None:
    s = await db.stats()
    users = await db.count_users()
    text = (
        "📊 <b>Statistik Toko</b>\n"
        f"{'─' * 22}\n"
        f"👥 Pengguna: <b>{users}</b>\n"
        f"✅ Terjual: <b>{s['sold']}</b>\n"
        f"⏳ Pending: <b>{s['pending']}</b>\n"
        f"💰 Omzet: <b>Rp {s['revenue']:,}</b>"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Kembali", callback_data="admin:home")
    await call.message.edit_text(text, reply_markup=kb.as_markup())
    await call.answer()


# ---------------- Tambah produk (FSM) ----------------
@router.callback_query(F.data == "admin:add")
async def cb_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddProduct.name)
    await call.message.edit_text("📝 Kirim <b>nama produk</b>:")
    await call.answer()


@router.message(AddProduct.name)
async def add_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(AddProduct.desc)
    await message.answer("📄 Kirim <b>deskripsi</b> (atau ketik <code>-</code> utk kosong):")


@router.message(AddProduct.desc)
async def add_desc(message: Message, state: FSMContext) -> None:
    desc = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(desc=desc)
    await state.set_state(AddProduct.emoji)
    await message.answer("😀 Kirim <b>1 emoji</b> ikon produk (atau <code>-</code>):")


@router.message(AddProduct.emoji)
async def add_emoji(message: Message, state: FSMContext) -> None:
    emoji = "📦" if message.text.strip() == "-" else message.text.strip()[:4]
    await state.update_data(emoji=emoji)
    await state.set_state(AddProduct.price)
    await message.answer("💵 Kirim <b>harga</b> (angka saja, contoh 145000):")


@router.message(AddProduct.price)
async def add_price(message: Message, state: FSMContext) -> None:
    raw = message.text.strip().replace(".", "").replace(",", "")
    if not raw.isdigit():
        await message.answer("❌ Harga harus angka. Coba lagi:")
        return
    await state.update_data(price=int(raw))
    await state.set_state(AddProduct.ptype)
    kb = InlineKeyboardBuilder()
    kb.button(text="🔑 Digital (auto-kirim)", callback_data="ptype:digital")
    kb.button(text="🛠️ Jasa/Manual", callback_data="ptype:service")
    kb.adjust(1)
    await message.answer(
        "Pilih <b>jenis produk</b>:\n"
        "• <b>Digital</b> = stok berupa akun/kode, dikirim otomatis saat lunas\n"
        "• <b>Jasa</b> = dikerjakan admin manual",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(AddProduct.ptype, F.data.startswith("ptype:"))
async def add_ptype(call: CallbackQuery, state: FSMContext) -> None:
    ptype = call.data.split(":")[1]
    await state.update_data(ptype=ptype)
    if ptype == "service":
        await state.set_state(AddProduct.stock)
        await call.message.edit_text("📦 Kirim jumlah <b>stok</b> awal (angka):")
    else:
        # Produk digital: stok berasal dari item yg ditambahkan nanti.
        await _finish_add(call.message, state, stock=0)
    await call.answer()


@router.message(AddProduct.stock)
async def add_stock(message: Message, state: FSMContext) -> None:
    if not message.text.strip().isdigit():
        await message.answer("❌ Harus angka. Coba lagi:")
        return
    await _finish_add(message, state, stock=int(message.text.strip()))


async def _finish_add(message: Message, state: FSMContext, stock: int) -> None:
    d = await state.get_data()
    pid = await db.add_product(
        d["name"], d["price"], d["desc"], d["emoji"], d["ptype"], stock
    )
    await state.clear()
    extra = ""
    if d["ptype"] == "digital":
        extra = (
            f"\n\nℹ️ Ini produk digital. Tambahkan stok (akun/kode) lewat "
            f"<b>Kelola Produk → produk ini → Tambah Stok</b>."
        )
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Kelola Produk", callback_data="admin:list")
    kb.button(text="⬅️ Panel Admin", callback_data="admin:home")
    kb.adjust(1)
    await message.answer(
        f"✅ Produk <b>{d['name']}</b> dibuat (ID {pid}).{extra}",
        reply_markup=kb.as_markup(),
    )


# ---------------- Kelola / hapus produk ----------------
@router.callback_query(F.data == "admin:list")
async def cb_list(call: CallbackQuery) -> None:
    products = await db.list_products(active_only=False)
    if not products:
        await call.answer("Belum ada produk.", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    for p in products:
        tag = "🟢" if p["is_active"] else "🔴"
        kb.button(
            text=f"{tag} {p['emoji']} {p['name']} (stok {p['available']})",
            callback_data=f"padm:{p['id']}",
        )
    kb.button(text="⬅️ Kembali", callback_data="admin:home")
    kb.adjust(1)
    await call.message.edit_text("📦 <b>Kelola Produk</b>", reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("padm:"))
async def cb_product_admin(call: CallbackQuery) -> None:
    pid = int(call.data.split(":")[1])
    p = await db.get_product(pid)
    if not p:
        await call.answer("Tidak ada.", show_alert=True)
        return
    text = (
        f"{p['emoji']} <b>{p['name']}</b> (ID {pid})\n"
        f"Harga: Rp {p['price']:,}\n"
        f"Jenis: {p['type']}\n"
        f"Stok: {p['available']}\n"
        f"Aktif: {'ya' if p['is_active'] else 'tidak'}"
    )
    kb = InlineKeyboardBuilder()
    if p["type"] == "digital":
        kb.button(text="➕ Tambah Stok", callback_data=f"stock:{pid}")
    kb.button(
        text=("🔴 Nonaktifkan" if p["is_active"] else "🟢 Aktifkan"),
        callback_data=f"toggle:{pid}",
    )
    kb.button(text="🗑️ Hapus", callback_data=f"del:{pid}")
    kb.button(text="⬅️ Kembali", callback_data="admin:list")
    kb.adjust(1)
    await call.message.edit_text(text, reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("toggle:"))
async def cb_toggle(call: CallbackQuery) -> None:
    pid = int(call.data.split(":")[1])
    p = await db.get_product(pid)
    await db.update_product_field(pid, "is_active", 0 if p["is_active"] else 1)
    await cb_product_admin(call)


@router.callback_query(F.data.startswith("del:"))
async def cb_del(call: CallbackQuery) -> None:
    pid = int(call.data.split(":")[1])
    await db.delete_product(pid)
    await call.answer("Produk dihapus.", show_alert=True)
    await cb_list(call)


@router.callback_query(F.data.startswith("stock:"))
async def cb_stock(call: CallbackQuery, state: FSMContext) -> None:
    pid = int(call.data.split(":")[1])
    await state.set_state(AddStock.items)
    await state.update_data(pid=pid)
    await call.message.edit_text(
        "➕ Kirim stok baru. <b>Satu baris = satu barang</b>.\n"
        "Contoh:\n<code>user1:pass1\nuser2:pass2</code>"
    )
    await call.answer()


@router.message(AddStock.items)
async def add_stock_items(message: Message, state: FSMContext) -> None:
    d = await state.get_data()
    lines = [ln.strip() for ln in message.text.splitlines() if ln.strip()]
    n = await db.add_items(d["pid"], lines)
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Kembali", callback_data=f"padm:{d['pid']}")
    await message.answer(f"✅ {n} item stok ditambahkan.", reply_markup=kb.as_markup())


# ---------------- Broadcast ----------------
@router.callback_query(F.data == "admin:bc")
async def cb_bc(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Broadcast.text)
    await call.message.edit_text("📢 Kirim pesan yang mau di-broadcast ke semua user:")
    await call.answer()


@router.message(Broadcast.text)
async def do_broadcast(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    user_ids = await db.all_user_ids()
    ok = fail = 0
    status = await message.answer(f"📤 Mengirim ke {len(user_ids)} user…")
    for uid in user_ids:
        try:
            await bot.copy_message(uid, message.chat.id, message.message_id)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)  # hindari flood limit
    await status.edit_text(f"✅ Broadcast selesai. Berhasil {ok}, gagal {fail}.")

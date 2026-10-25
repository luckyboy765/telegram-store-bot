"""Logika ketika sebuah order LUNAS: kirim barang & beri tahu admin.

Dipanggil dari dua sumber (polling & webhook), jadi dibuat idempoten:
kalau order sudah 'delivered'/'paid' diproses, tidak dikirim dua kali.
"""
from __future__ import annotations

import logging

from aiogram import Bot

import database as db
from config import ADMIN_IDS

log = logging.getLogger(__name__)


async def fulfill_order(bot: Bot, order_id: int) -> None:
    order = await db.get_order(order_id)
    if not order:
        return
    if order["status"] in ("delivered",):
        return  # sudah dikirim, jangan dobel

    await db.set_order_status(order_id, "paid", paid=True)

    product = await db.get_product(order["product_id"])
    user_id = order["user_id"]

    if product and product["type"] == "digital":
        content = await db.deliver_digital_item(order_id, product["id"])
        if content:
            await bot.send_message(
                user_id,
                f"✅ <b>Pembayaran diterima!</b>\n\n"
                f"📦 <b>{order['product_name']}</b>\n"
                f"Order #{order_id}\n\n"
                f"Berikut barang kamu:\n<code>{content}</code>\n\n"
                f"Terima kasih sudah belanja! 🙏",
            )
        else:
            # Uang masuk tapi stok habis -> eskalasi ke admin, jangan diamkan.
            await bot.send_message(
                user_id,
                f"✅ Pembayaran untuk order #{order_id} diterima.\n"
                f"⚠️ Stok sedang kosong, admin akan mengirim manual secepatnya.",
            )
            await _notify_admins(
                bot,
                f"🚨 Order #{order_id} LUNAS tapi STOK HABIS!\n"
                f"Produk: {order['product_name']}\nUser: {user_id}\n"
                f"Segera kirim manual / refund.",
            )
            return
    else:
        # Produk jasa/manual: kurangi stok, minta admin proses.
        if product:
            new_stock = max(0, product["stock"] - 1)
            await db.update_product_field(product["id"], "stock", new_stock)
        await db.set_order_status(order_id, "delivered")
        await bot.send_message(
            user_id,
            f"✅ <b>Pembayaran diterima!</b>\n\n"
            f"📦 <b>{order['product_name']}</b> (Order #{order_id})\n\n"
            f"Pesanan kamu akan diproses admin. Mohon tunggu ya 🙏",
        )

    await _notify_admins(
        bot,
        f"💰 <b>Order LUNAS</b> #{order_id}\n"
        f"Produk: {order['product_name']}\n"
        f"Jumlah: Rp {order['amount']:,}\n"
        f"User: <code>{user_id}</code>",
    )


async def _notify_admins(bot: Bot, text: str) -> None:
    for admin in ADMIN_IDS:
        try:
            await bot.send_message(admin, text)
        except Exception as e:  # admin belum pernah /start ke bot, dsb
            log.warning("Gagal kirim ke admin %s: %s", admin, e)

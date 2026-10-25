"""Web server kecil untuk menerima callback pembayaran dari Tripay.

Hanya aktif kalau WEBHOOK_HOST diisi di .env. Kalau tidak, bot pakai polling
(lihat handlers/user.py) sehingga tetap otomatis tanpa perlu buka port.

Set Callback URL di dashboard Tripay ke:  {WEBHOOK_HOST}/callback
"""
from __future__ import annotations

import json
import logging

from aiogram import Bot
from aiohttp import web

import database as db
from delivery import fulfill_order
from payments import provider

log = logging.getLogger(__name__)


async def _handle_callback(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]
    raw = await request.read()
    signature = request.headers.get("X-Callback-Signature", "")

    if not provider.verify_callback(raw, signature):
        log.warning("Callback signature tidak valid")
        return web.json_response({"success": False}, status=403)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return web.json_response({"success": False}, status=400)

    reference = data.get("reference")
    status = data.get("status")  # PAID / EXPIRED / FAILED
    order = await db.get_order_by_reference(reference) if reference else None
    if not order:
        return web.json_response({"success": True})  # bukan order kita, abaikan

    if status == "PAID":
        await fulfill_order(bot, order["id"])
    elif status in ("EXPIRED", "FAILED"):
        await db.set_order_status(order["id"], "expired")

    return web.json_response({"success": True})


async def _health(_: web.Request) -> web.Response:
    return web.Response(text="ok")


def build_app(bot: Bot) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/callback", _handle_callback)
    app.router.add_get("/", _health)
    return app

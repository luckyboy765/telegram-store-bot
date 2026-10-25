"""Titik masuk bot toko.

Jalankan:  python bot.py

- Selalu polling Telegram (getUpdates).
- Kalau WEBHOOK_HOST diisi, sekaligus menyalakan web server callback Tripay.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

import config
import database as db
from handlers import admin, user

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("store-bot")


async def _resume_pending(bot: Bot) -> None:
    """Setelah restart, lanjutkan pantau order yang masih pending."""
    from payments import provider
    from handlers.user import _poll_order

    for order in await db.pending_orders():
        asyncio.create_task(_poll_order(bot, order["id"], order["reference"]))


async def main() -> None:
    config.validate()
    await db.init_db()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    # admin dulu supaya FSM state admin diproses sebelum handler user generik.
    dp.include_router(admin.router)
    dp.include_router(user.router)

    await _resume_pending(bot)

    runner = None
    if config.USE_WEBHOOK:
        from webhook import build_app

        app = build_app(bot)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", config.WEBHOOK_PORT)
        await site.start()
        log.info("Webhook callback aktif di port %s (%s/callback)",
                 config.WEBHOOK_PORT, config.WEBHOOK_HOST)
    else:
        log.info("Mode POLLING gateway (tanpa webhook).")

    log.info("Bot '%s' jalan. Admin: %s", config.STORE_NAME, config.ADMIN_IDS)
    try:
        await dp.start_polling(bot)
    finally:
        if runner:
            await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit) as e:
        if isinstance(e, SystemExit) and e.code:
            raise
        print("Bot dihentikan.")

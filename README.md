# Telegram Store Bot with QRIS Auto-Payment

A Telegram shop for digital products and services. Customers browse a catalog,
pay with QRIS through the Tripay payment gateway, and digital items are
delivered automatically the moment the payment clears.

Built with **Python, aiogram 3, aiosqlite and aiohttp**.

## Features

- Product catalog with pagination and live stock
- Automatic QRIS payment (Tripay), no admin needed to confirm
- Two product types:
  - **digital**: codes/accounts delivered instantly after payment
  - **service**: admin is notified and handles the order
- Order history for customers
- In-bot admin panel (`/admin`): add/edit/delete products, add stock,
  sales stats, broadcast
- **No double selling**: stock is reserved inside a database transaction
- **Idempotent payment handling**: webhook and polling can both run safely
- **Demo mode**: with empty Tripay credentials the bot still works and
  invoices auto-complete after 20 seconds, for testing without real money

## How payment confirmation works

1. Customer taps **Buy**, the bot requests an invoice and shows the QRIS code.
2. Payment is confirmed through whichever path arrives first:
   - **Webhook**: Tripay calls `{WEBHOOK_HOST}/callback` (signature verified)
   - **Polling**: the bot checks the invoice status every 6 seconds
3. On success, digital items are sent automatically; service orders go to admin.

Both paths call the same idempotent "mark as paid" step, so an order is never
delivered twice.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # fill BOT_TOKEN and ADMIN_IDS at minimum
python seed.py            # optional: add sample products
python bot.py
```

Open the bot in Telegram and send `/start`. Admins send `/admin`.

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | yes | Token from @BotFather |
| `ADMIN_IDS` | yes | Telegram user IDs of admins, comma separated |
| `TRIPAY_*` | no | Tripay merchant credentials. Empty = demo mode |
| `WEBHOOK_HOST` | no | Public URL for payment callbacks. Empty = polling |

## Project structure

```
bot.py            entry point, dispatcher and background tasks
config.py         settings loaded from .env
database.py       SQLite schema and queries (orders, products, stock)
delivery.py       paid-order handling and item delivery
handlers/user.py  catalog, checkout, order history
handlers/admin.py admin panel (FSM forms), stats, broadcast
keyboards.py      inline keyboards
payments/         provider interface, Tripay and demo implementations
webhook.py        aiohttp server for payment callbacks
seed.py           sample products
```

The payment layer sits behind a small `PaymentProvider` interface, so another
gateway (Midtrans, Xendit, Duitku...) can be added without touching the bot logic.

## Deployment

Runs well as a systemd service on a small Linux VPS. Put secrets in `.env`
(never commit it) and set `Restart=always` so the bot comes back after a crash
or reboot.

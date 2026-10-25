"""Konfigurasi terpusat, dibaca dari file .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _int_list(raw: str) -> list[int]:
    return [int(x) for x in raw.replace(" ", "").split(",") if x]


# ---- Telegram ----
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_IDS: list[int] = _int_list(os.getenv("ADMIN_IDS", ""))

# ---- Toko ----
STORE_NAME: str = os.getenv("STORE_NAME", "MY STORE")
PRODUCTS_PER_PAGE: int = int(os.getenv("PRODUCTS_PER_PAGE", "5"))
INVOICE_EXPIRE_MINUTES: int = int(os.getenv("INVOICE_EXPIRE_MINUTES", "15"))

# ---- Tripay ----
TRIPAY_API_KEY: str = os.getenv("TRIPAY_API_KEY", "")
TRIPAY_PRIVATE_KEY: str = os.getenv("TRIPAY_PRIVATE_KEY", "")
TRIPAY_MERCHANT_CODE: str = os.getenv("TRIPAY_MERCHANT_CODE", "")
TRIPAY_SANDBOX: bool = os.getenv("TRIPAY_SANDBOX", "true").lower() == "true"
TRIPAY_CHANNEL: str = os.getenv("TRIPAY_CHANNEL", "QRIS")

# ---- Webhook ----
WEBHOOK_HOST: str = os.getenv("WEBHOOK_HOST", "").rstrip("/")
WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8080"))
USE_WEBHOOK: bool = bool(WEBHOOK_HOST)

DB_PATH = BASE_DIR / "store.db"


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def validate() -> None:
    """Berhenti lebih awal kalau konfigurasi wajib belum diisi."""
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not ADMIN_IDS:
        missing.append("ADMIN_IDS")
    if missing:
        raise SystemExit(
            "Konfigurasi wajib belum diisi di .env: " + ", ".join(missing)
        )

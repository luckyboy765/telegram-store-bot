"""Factory pemilih payment gateway.

Kalau kredensial Tripay belum diisi, otomatis pakai DemoProvider supaya bot
tetap bisa dites end-to-end (invoice-nya langsung "lunas" setelah beberapa detik).
"""
from __future__ import annotations

import time

from config import TRIPAY_API_KEY, TRIPAY_MERCHANT_CODE, TRIPAY_PRIVATE_KEY
from payments.base import Invoice, PaymentProvider
from payments.tripay import TripayProvider


class DemoProvider(PaymentProvider):
    """Gateway palsu buat testing tanpa akun asli."""

    _seen: dict[str, float] = {}

    async def create_invoice(self, order_ref, amount, product_name, customer) -> Invoice:
        ref = f"DEMO-{order_ref}-{int(time.time())}"
        self._seen[ref] = time.time()
        return Invoice(
            reference=ref,
            amount=amount,
            pay_url="https://example.com/demo-checkout",
            qr_url="https://api.qrserver.com/v1/create-qr-code/?size=300x300&data="
                   + ref,
            expired_at=int(time.time()) + 900,
        )

    async def check_status(self, reference: str) -> str:
        # Anggap lunas 20 detik setelah invoice dibuat.
        started = self._seen.get(reference, 0)
        return "PAID" if time.time() - started > 20 else "PENDING"


def get_provider() -> PaymentProvider:
    if TRIPAY_API_KEY and TRIPAY_PRIVATE_KEY and TRIPAY_MERCHANT_CODE:
        return TripayProvider()
    return DemoProvider()


provider: PaymentProvider = get_provider()

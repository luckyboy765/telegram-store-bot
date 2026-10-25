"""Antarmuka umum payment gateway.

Ganti gateway (Midtrans, dsb) cukup dengan bikin kelas baru yang mewarisi
PaymentProvider dan mengembalikan Invoice yang sama bentuknya.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Invoice:
    reference: str            # id transaksi di sisi gateway
    amount: int               # total yang harus dibayar (sudah termasuk fee)
    pay_url: str              # halaman bayar (checkout)
    qr_url: Optional[str]     # gambar QRIS (kalau ada)
    expired_at: Optional[int] # epoch detik


class PaymentProvider:
    async def create_invoice(
        self, order_ref: str, amount: int, product_name: str, customer: str
    ) -> Invoice:
        raise NotImplementedError

    async def check_status(self, reference: str) -> str:
        """Kembalikan salah satu: 'PENDING' | 'PAID' | 'EXPIRED' | 'FAILED'."""
        raise NotImplementedError

    def verify_callback(self, raw_body: bytes, signature: str) -> bool:
        """Validasi tanda tangan callback. Default True (dipakai gateway tanpa signature)."""
        return True

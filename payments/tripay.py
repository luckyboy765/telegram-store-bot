"""Implementasi Tripay (https://tripay.co.id) — mendukung QRIS.

Alur:
1. create_invoice  -> POST /transaction/create  (dapat reference, checkout_url, qr_url)
2. check_status    -> GET  /transaction/detail    (polling status)
3. verify_callback -> cek header X-Callback-Signature (HMAC-SHA256 private_key)
"""
from __future__ import annotations

import hashlib
import hmac
import time

import aiohttp

from config import (
    INVOICE_EXPIRE_MINUTES,
    TRIPAY_API_KEY,
    TRIPAY_CHANNEL,
    TRIPAY_MERCHANT_CODE,
    TRIPAY_PRIVATE_KEY,
    TRIPAY_SANDBOX,
)
from payments.base import Invoice, PaymentProvider

_STATUS_MAP = {
    "UNPAID": "PENDING",
    "PAID": "PAID",
    "EXPIRED": "EXPIRED",
    "FAILED": "FAILED",
    "REFUND": "FAILED",
}


class TripayProvider(PaymentProvider):
    def __init__(self) -> None:
        host = "tripay.co.id/api-sandbox" if TRIPAY_SANDBOX else "tripay.co.id/api"
        self.base = f"https://{host}"
        self.headers = {"Authorization": f"Bearer {TRIPAY_API_KEY}"}

    def _signature(self, merchant_ref: str, amount: int) -> str:
        raw = f"{TRIPAY_MERCHANT_CODE}{merchant_ref}{amount}".encode()
        return hmac.new(TRIPAY_PRIVATE_KEY.encode(), raw, hashlib.sha256).hexdigest()

    async def create_invoice(
        self, order_ref: str, amount: int, product_name: str, customer: str
    ) -> Invoice:
        payload = {
            "method": TRIPAY_CHANNEL,
            "merchant_ref": order_ref,
            "amount": amount,
            "customer_name": customer or "Pembeli",
            "customer_email": "buyer@example.com",
            "order_items": [
                {"name": product_name[:50], "price": amount, "quantity": 1}
            ],
            "expired_time": int(time.time()) + INVOICE_EXPIRE_MINUTES * 60,
            "signature": self._signature(order_ref, amount),
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{self.base}/transaction/create", json=payload, headers=self.headers
            ) as r:
                data = await r.json()
        if not data.get("success"):
            raise RuntimeError(f"Tripay error: {data.get('message', data)}")
        d = data["data"]
        return Invoice(
            reference=d["reference"],
            amount=d["amount"],
            pay_url=d["checkout_url"],
            qr_url=d.get("qr_url") or d.get("qr_string"),
            expired_at=d.get("expired_time"),
        )

    async def check_status(self, reference: str) -> str:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{self.base}/transaction/detail",
                params={"reference": reference},
                headers=self.headers,
            ) as r:
                data = await r.json()
        if not data.get("success"):
            return "PENDING"
        return _STATUS_MAP.get(data["data"]["status"], "PENDING")

    def verify_callback(self, raw_body: bytes, signature: str) -> bool:
        expected = hmac.new(
            TRIPAY_PRIVATE_KEY.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature or "")

"""Isi database dengan produk contoh biar bisa langsung dites.

Jalankan sekali:  python seed.py
"""
import asyncio

import database as db


async def main() -> None:
    await db.init_db()

    # Produk digital (stok = item yang ditambahkan)
    pid = await db.add_product(
        name="Akun Streaming 1 Bulan",
        price=15000,
        description="Akun sharing legal, garansi 30 hari.",
        emoji="🎬",
        ptype="digital",
        stock=0,
    )
    await db.add_items(pid, [
        "email1@mail.com | pass123 | profil 1",
        "email2@mail.com | pass456 | profil 2",
        "email3@mail.com | pass789 | profil 3",
    ])

    pid2 = await db.add_product(
        name="Voucher Game 100 Diamond",
        price=25000,
        description="Kode voucher dikirim otomatis setelah bayar.",
        emoji="💎",
        ptype="digital",
        stock=0,
    )
    await db.add_items(pid2, ["KODE-AAA-111", "KODE-BBB-222"])

    # Produk jasa (stok manual, admin yang proses)
    await db.add_product(
        name="Jasa Setup VPS",
        price=50000,
        description="Instalasi & konfigurasi VPS sesuai kebutuhan. Diproses admin.",
        emoji="🛠️",
        ptype="service",
        stock=10,
    )

    print("✅ Seed selesai. Jalankan: python bot.py")


if __name__ == "__main__":
    asyncio.run(main())

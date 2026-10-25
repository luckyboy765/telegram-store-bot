"""Lapisan database SQLite (async pakai aiosqlite).

Skema:
- users          : siapa saja yang pernah /start
- products       : katalog. type = 'digital' (auto kirim) atau 'service' (manual)
- product_items  : stok item digital (tiap baris = 1 barang yang bisa dikirim)
- orders         : transaksi
"""
from __future__ import annotations

import time
from typing import Any, Optional

import aiosqlite

from config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    username    TEXT,
    first_name  TEXT,
    joined_at   INTEGER
);

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    emoji       TEXT DEFAULT '📦',
    price       INTEGER NOT NULL,           -- rupiah, integer
    type        TEXT NOT NULL DEFAULT 'digital', -- 'digital' | 'service'
    stock       INTEGER NOT NULL DEFAULT 0, -- dipakai utk type 'service'
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  INTEGER
);

CREATE TABLE IF NOT EXISTS product_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL,
    content     TEXT NOT NULL,              -- barang yang dikirim (akun, kode, dsb)
    is_sold     INTEGER NOT NULL DEFAULT 0,
    order_id    INTEGER,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    product_id  INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    amount      INTEGER NOT NULL,           -- total yang harus dibayar
    status      TEXT NOT NULL DEFAULT 'pending', -- pending|paid|delivered|expired|failed
    reference   TEXT,                       -- referensi dari Tripay
    pay_url     TEXT,
    qr_url      TEXT,
    delivered   TEXT DEFAULT '',            -- isi yang sudah dikirim ke user
    created_at  INTEGER,
    paid_at     INTEGER
);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


# ---------- Users ----------
async def upsert_user(user_id: int, username: Optional[str], first_name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users (id, username, first_name, joined_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET username=excluded.username,
                                             first_name=excluded.first_name""",
            (user_id, username, first_name, int(time.time())),
        )
        await db.commit()


async def count_users() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users")
        (n,) = await cur.fetchone()
        return n


async def all_user_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id FROM users")
        return [row[0] for row in await cur.fetchall()]


# ---------- Products ----------
def _row_to_dict(cursor, row) -> dict[str, Any]:
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


async def stock_of(db: aiosqlite.Connection, product: dict) -> int:
    """Stok efektif: item digital yang belum terjual, atau kolom stock utk service."""
    if product["type"] == "digital":
        # Caller memasang row_factory=dict, jadi baca via alias kolom (bukan unpack tuple).
        cur = await db.execute(
            "SELECT COUNT(*) AS c FROM product_items WHERE product_id=? AND is_sold=0",
            (product["id"],),
        )
        row = await cur.fetchone()
        return row["c"]
    return product["stock"]


async def list_products(active_only: bool = True) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = _row_to_dict
        q = "SELECT * FROM products"
        if active_only:
            q += " WHERE is_active=1"
        q += " ORDER BY id"
        cur = await db.execute(q)
        products = await cur.fetchall()
        for p in products:
            p["available"] = await stock_of(db, p)
        return products


async def get_product(product_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = _row_to_dict
        cur = await db.execute("SELECT * FROM products WHERE id=?", (product_id,))
        p = await cur.fetchone()
        if p:
            p["available"] = await stock_of(db, p)
        return p


async def add_product(
    name: str, price: int, description: str, emoji: str, ptype: str, stock: int
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO products (name, description, emoji, price, type, stock, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, description, emoji, price, ptype, stock, int(time.time())),
        )
        await db.commit()
        return cur.lastrowid


async def update_product_field(product_id: int, field: str, value: Any) -> None:
    if field not in {"name", "description", "emoji", "price", "type", "stock", "is_active"}:
        raise ValueError(f"Field tidak diizinkan: {field}")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE products SET {field}=? WHERE id=?", (value, product_id))
        await db.commit()


async def delete_product(product_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM product_items WHERE product_id=?", (product_id,))
        await db.execute("DELETE FROM products WHERE id=?", (product_id,))
        await db.commit()


async def add_items(product_id: int, contents: list[str]) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT INTO product_items (product_id, content) VALUES (?, ?)",
            [(product_id, c) for c in contents],
        )
        await db.commit()
        return len(contents)


# ---------- Orders ----------
async def create_order(
    user_id: int, product: dict, amount: int, reference: str, pay_url: str, qr_url: str
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO orders (user_id, product_id, product_name, amount, status,
                                   reference, pay_url, qr_url, created_at)
               VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
            (user_id, product["id"], product["name"], amount, reference,
             pay_url, qr_url, int(time.time())),
        )
        await db.commit()
        return cur.lastrowid


async def get_order(order_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = _row_to_dict
        cur = await db.execute("SELECT * FROM orders WHERE id=?", (order_id,))
        return await cur.fetchone()


async def get_order_by_reference(reference: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = _row_to_dict
        cur = await db.execute("SELECT * FROM orders WHERE reference=?", (reference,))
        return await cur.fetchone()


async def set_order_status(order_id: int, status: str, paid: bool = False) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        if paid:
            await db.execute(
                "UPDATE orders SET status=?, paid_at=? WHERE id=?",
                (status, int(time.time()), order_id),
            )
        else:
            await db.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        await db.commit()


async def pending_orders() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = _row_to_dict
        cur = await db.execute("SELECT * FROM orders WHERE status='pending'")
        return await cur.fetchall()


async def deliver_digital_item(order_id: int, product_id: int) -> Optional[str]:
    """Ambil 1 item yang belum terjual, tandai terjual, kembalikan isinya.

    Pakai transaksi + kondisi is_sold=0 supaya tidak ada dobel-jual (race)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = _row_to_dict
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute(
            "SELECT * FROM product_items WHERE product_id=? AND is_sold=0 LIMIT 1",
            (product_id,),
        )
        item = await cur.fetchone()
        if not item:
            await db.commit()
            return None
        await db.execute(
            "UPDATE product_items SET is_sold=1, order_id=? WHERE id=?",
            (order_id, item["id"]),
        )
        await db.execute(
            "UPDATE orders SET status='delivered', delivered=? WHERE id=?",
            (item["content"], order_id),
        )
        await db.commit()
        return item["content"]


async def stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = _row_to_dict
        cur = await db.execute(
            """SELECT
                 COUNT(*) FILTER (WHERE status IN ('paid','delivered'))          AS sold,
                 COALESCE(SUM(amount) FILTER (WHERE status IN ('paid','delivered')),0) AS revenue,
                 COUNT(*) FILTER (WHERE status='pending')                        AS pending
               FROM orders"""
        )
        return await cur.fetchone()

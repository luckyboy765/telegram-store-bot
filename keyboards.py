"""Semua inline keyboard di satu tempat."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import PRODUCTS_PER_PAGE


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍️ Katalog Produk", callback_data="catalog:0")
    kb.button(text="🧾 Pesanan Saya", callback_data="myorders")
    if is_admin:
        kb.button(text="⚙️ Panel Admin", callback_data="admin:home")
    kb.adjust(1)
    return kb.as_markup()


def catalog_kb(products: list[dict], page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    start = page * PRODUCTS_PER_PAGE
    chunk = products[start : start + PRODUCTS_PER_PAGE]
    for p in chunk:
        if p["available"] <= 0:
            harga = "HABIS"
        else:
            harga = "Rp {:,}".format(p["price"])
        label = "{} {} — {}".format(p["emoji"], p["name"], harga)
        kb.button(text=label, callback_data="prod:{}:{}".format(p["id"], page))
    kb.adjust(1)

    # Navigasi halaman
    total_pages = max(1, (len(products) + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"catalog:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if start + PRODUCTS_PER_PAGE < len(products):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"catalog:{page+1}"))
    if nav:
        kb.row(*nav)

    kb.row(InlineKeyboardButton(text="🏠 Menu Utama", callback_data="home"))
    return kb.as_markup()


def product_kb(product: dict, page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if product["available"] > 0:
        kb.button(text="✅ Beli Sekarang", callback_data=f"buy:{product['id']}")
    kb.button(text="⬅️ Kembali", callback_data=f"catalog:{page}")
    kb.adjust(1)
    return kb.as_markup()


def invoice_kb(order_id: int, pay_url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if pay_url:
        kb.button(text="🌐 Buka Halaman Bayar", url=pay_url)
    kb.button(text="🔄 Cek Status Bayar", callback_data=f"check:{order_id}")
    kb.button(text="❌ Batalkan", callback_data=f"cancel:{order_id}")
    kb.adjust(1)
    return kb.as_markup()


def back_home() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Menu Utama", callback_data="home")
    return kb.as_markup()

"""Prices by delivery country.

- The store's own catalogue currency (store_profile.currency, USD for both stores) is used for US delivery: exactly the
  prices in `products`, as always.
- India delivery uses INR, and ONLY prices the owner has approved into `product_prices` (migration 0008). There is no
  exchange rate anywhere: a product without an approved INR price has no INR price, it is shown as "price not set" and
  cannot be ordered for India. USD amounts are never shown, charged or relabelled for an Indian address.

Approving a list (owner action, e.g. from a reviewed CSV): INSERT INTO product_prices (product_id, currency, price_minor,
approved_by) … — amounts in paise. See docs/india-readiness.md.
"""

from __future__ import annotations

from typing import Any, Iterable

from . import repositories as repo
from .repositories import store_connection
from .stores import StoreId

CURRENCY_BY_COUNTRY = {"IN": "INR"}
SUPPORTED_CURRENCIES = ("USD", "INR")


def base_currency(store: StoreId) -> str:
    return (repo.get_shipping_rates(store).get("currency") or "USD").strip().upper()


def currency_for_country(store: StoreId, country: str | None) -> str:
    return CURRENCY_BY_COUNTRY.get(country or "", base_currency(store))


def approved_prices(store: StoreId, currency: str, product_ids: Iterable[int] | None = None, conn=None) -> dict[int, int]:
    """product_id → approved price (minor units) in `currency`. Only rows in product_prices; never derived."""
    sql = "SELECT product_id, price_minor FROM product_prices WHERE currency = %s"
    args: list[Any] = [currency]
    if product_ids is not None:
        ids = list(product_ids)
        if not ids:
            return {}
        sql += " AND product_id = ANY(%s)"
        args.append(ids)
    if conn is not None:
        return {r["product_id"]: r["price_minor"] for r in conn.execute(sql, args).fetchall()}
    with store_connection(store) as c:
        return {r["product_id"]: r["price_minor"] for r in c.execute(sql, args).fetchall()}


def prices_for(store: StoreId, currency: str, rows: list[dict[str, Any]], conn=None) -> dict[int, int | None]:
    """product id → price in `currency` (None = not set). The catalogue currency uses products.price_cents."""
    if currency == base_currency(store):
        return {r["id"] if "id" in r else r["product_id"]: r["price_cents"] for r in rows}
    ids = [r["id"] if "id" in r else r["product_id"] for r in rows]
    approved = approved_prices(store, currency, ids, conn)
    return {i: approved.get(i) for i in ids}


def price_list_status(store: StoreId) -> dict[str, Any]:
    """For the storefront: catalogue currency and how complete each other currency's approved list is."""
    with store_connection(store) as conn:
        total = conn.execute("SELECT count(*) AS n FROM products").fetchone()["n"]
        rows = conn.execute("SELECT currency, count(*) AS n FROM product_prices GROUP BY currency").fetchall()
    have = {r["currency"].strip(): r["n"] for r in rows}
    base = base_currency(store)
    return {"base_currency": base, "products": total,
            "currencies": {c: {"approved": (total if c == base else have.get(c, 0)),
                               "complete": c == base or (total > 0 and have.get(c, 0) >= total)} for c in SUPPORTED_CURRENCIES}}


# ---- the store's selling currency (India-only project: INR) -------------------------------------------------------------
def selling_currency(markets: dict[str, str], store: StoreId) -> str:
    """The currency a store sells in: its market's (INR for India). Never the catalogue's USD for an India store."""
    from .markets import MARKETS
    return MARKETS[markets.get(store.value, "US")].currency


def localize(store: StoreId, rows: list[dict[str, Any]], currency: str, conn=None) -> list[dict[str, Any]]:
    """Product rows with price_cents in `currency` (None where no price is approved — never converted) and a `currency`
    key. The catalogue's own amount is kept as catalogue_price_cents for internal use only."""
    if not rows:
        return []
    prices = prices_for(store, currency, rows, conn)
    key = "id" if "id" in rows[0] else "product_id"
    return [{**r, "catalogue_price_cents": r["price_cents"], "price_cents": prices.get(r[key]), "currency": currency} for r in rows]

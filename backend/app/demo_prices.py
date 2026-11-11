"""Academic demonstration INR price list (config/pricing/demo-inr-prices.json) → product_prices.

These are fixed rupee amounts chosen for the final-year demonstration — NOT commercial prices and NOT converted from the
USD catalogue (there is no exchange rate anywhere in this project). Each store's list goes only into that store's own
database. Rows are marked with the list's `approved_by` label so they can be told apart from any real price list.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg

from .config import PROJECT_ROOT

DEFAULT_LIST = PROJECT_ROOT / "config" / "pricing" / "demo-inr-prices.json"


def load_list(path: Path = DEFAULT_LIST) -> dict[str, Any]:
    data = json.loads(Path(path).read_text())
    label = data.get("approved_by")
    if not isinstance(label, str) or "demonstration" not in label:
        raise ValueError("the price list must carry an approved_by label that says it is a demonstration list")
    for store in ("store-a", "store-b"):
        prices = data.get(store)
        if not isinstance(prices, dict) or not prices:
            raise ValueError(f"no prices for {store}")
        for slug, paise in prices.items():
            if not isinstance(paise, int) or isinstance(paise, bool) or paise <= 0 or paise % 100:
                raise ValueError(f"{store} {slug}: price must be a positive whole-rupee amount in paise, got {paise!r}")
    return data


def apply(urls: dict[str, str], data: dict[str, Any], dry_run: bool = False) -> dict[str, dict[str, Any]]:
    """Upsert each store's list into that store's database. Refuses (changes nothing in that store) if a slug is unknown.
    Returns per store: {"products": n, "priced": n, "changed": [slugs], "missing": [slugs without a price]}."""
    report = {}
    for store, url in urls.items():
        prices = data[store]
        with psycopg.connect(url) as conn, conn.transaction():
            products = {r[0]: r[1] for r in conn.execute("SELECT slug, id FROM products").fetchall()}
            unknown = sorted(set(prices) - set(products))
            if unknown:
                raise ValueError(f"{store}: unknown products in the price list: {unknown}")
            current = {r[0]: r[1] for r in conn.execute(
                "SELECT p.slug, pp.price_minor FROM product_prices pp JOIN products p ON p.id = pp.product_id WHERE pp.currency = 'INR'").fetchall()}
            changed = sorted(s for s, v in prices.items() if current.get(s) != v)
            if not dry_run:
                for slug in changed:
                    conn.execute(
                        "INSERT INTO product_prices (product_id, currency, price_minor, approved_by) VALUES (%s, 'INR', %s, %s) "
                        "ON CONFLICT (product_id, currency) DO UPDATE SET price_minor = EXCLUDED.price_minor, "
                        "approved_by = EXCLUDED.approved_by, approved_at = now()",
                        [products[slug], prices[slug], data["approved_by"]])
            report[store] = {"products": len(products), "priced": len(set(prices) | set(current)), "changed": changed,
                             "missing": sorted(set(products) - set(prices) - set(current))}
    return report

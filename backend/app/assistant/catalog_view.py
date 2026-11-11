"""The assistants' view of the catalogue, priced exactly like the storefront.

Scout and Maple read products through this view only, so every price they quote, compare, filter by budget or show on a
product card comes from the same source as the storefront: the store's selling currency (INR for an India store) and
its approved price list (product_prices) — never the USD catalogue amount, never converted, never guessed. A product
without an approved price keeps price_cents None and is described as "price not set".
"""

from __future__ import annotations

from typing import Any

from .. import commerce
from .. import repositories as repo
from ..pricing import base_currency, localize, selling_currency
from ..stores import StoreId


class CatalogView:
    def __init__(self, markets: dict[str, str] | None = None, shipping_config_dir=None):
        self.markets = markets or {}
        self.shipping_config_dir = shipping_config_dir

    def market(self, store: StoreId) -> str:
        return self.markets.get(store.value, "US")

    def currency(self, store: StoreId) -> str:
        return selling_currency(self.markets, store)

    def _native(self, store: StoreId) -> bool:
        return self.currency(store) == base_currency(store)

    def _loc(self, store: StoreId, rows) -> list[dict[str, Any]]:
        return localize(store, list(rows), self.currency(store))

    def search(self, store: StoreId, terms: list[str], limit: int = 5, max_price_cents: int | None = None) -> list[dict[str, Any]]:
        if max_price_cents is None or self._native(store):
            return self._loc(store, repo.search_products_by_terms(store, terms, limit=limit, max_price_cents=max_price_cents))
        rows = self._loc(store, repo.search_products_by_terms(store, terms, limit=200))
        return [r for r in rows if r["price_cents"] is not None and r["price_cents"] <= max_price_cents][:limit]

    def recommend(self, store: StoreId, max_price_cents: int | None = None, limit: int = 3) -> list[dict[str, Any]]:
        if self._native(store):
            return self._loc(store, repo.recommend_products(store, max_price_cents, limit))
        rows = [r for r in self._loc(store, repo.recommend_products(store, None, limit=500))
                if r["price_cents"] is not None and (max_price_cents is None or r["price_cents"] <= max_price_cents)]
        return sorted(rows, key=lambda r: (-r["price_cents"], r["name"]))[:limit]

    def in_category(self, store: StoreId, category: str, limit: int = 500) -> list[dict[str, Any]]:
        return self._loc(store, repo.list_products(store, category=category, limit=limit))

    def mentioned_in(self, store: StoreId, text: str) -> list[dict[str, Any]]:
        return self._loc(store, repo.products_mentioned_in(store, text))

    def by_slug(self, store: StoreId, slug: str) -> dict[str, Any] | None:
        p = repo.get_product_by_slug(store, slug)
        return self._loc(store, [p])[0] if p else None

    def by_slugs(self, store: StoreId, slugs: list[str]) -> dict[str, dict[str, Any]]:
        rows = repo.get_products_by_slugs(store, slugs)
        return {p["slug"]: p for p in self._loc(store, rows.values())}

    def cart(self, store: StoreId, owner) -> dict[str, Any]:
        """The cart in the selling currency. For India, shipping is priced at checkout (it depends on the address)."""
        if self.market(store) == "US":
            return commerce.get_cart(store, owner)
        return commerce.get_cart(store, owner, rates=None, country=self.market(store))

    def free_shipping_threshold(self, store: StoreId) -> str | None:
        """The configured free-delivery threshold, formatted, if there is exactly one (demonstration) rule."""
        if self.market(store) == "US":
            rates = repo.get_shipping_rates(store)
            return commerce.money(rates["free_shipping_min_cents"]) if rates["free_shipping_min_cents"] is not None else None
        from ..shipping_zones import load_zones
        zones = load_zones(self.shipping_config_dir, store, self.market(store)) if self.shipping_config_dir else []
        frees = {(z.get("free_over_cents"), z["currency"]) for z in zones}
        if len(frees) == 1 and (f := next(iter(frees)))[0] is not None:
            return commerce.money(f[0], f[1])
        return None

    def shipping_rates(self, store: StoreId) -> dict[str, str]:
        """Shipping options to state in an answer (label → price), from the same configuration the checkout uses."""
        if self.market(store) == "US":
            rates = repo.get_shipping_rates(store)
            out = {o["label"]: o["price"] for o in commerce.shipping_options(rates, 1)}
            if rates["free_shipping_min_cents"] is not None:
                out["free_standard_shipping_from"] = commerce.money(rates["free_shipping_min_cents"])
            return out
        from ..shipping_zones import load_zones
        out = {}
        for z in load_zones(self.shipping_config_dir, store, self.market(store)) if self.shipping_config_dir else []:
            out[f"{z['name']}: standard delivery"] = commerce.money(z["standard_cents"], z["currency"])
            if z.get("free_over_cents") is not None:
                out[f"{z['name']}: free delivery from"] = commerce.money(z["free_over_cents"], z["currency"])
        return out

"""Registry of the stores this platform serves. The store id is the only key that
selects a database; it is validated against this registry on every request."""

from __future__ import annotations

from enum import Enum


class StoreId(str, Enum):
    STORE_A = "store-a"
    STORE_B = "store-b"


STORE_BRANDING: dict[StoreId, dict[str, str]] = {
    StoreId.STORE_A: {"name": "Summit Trail Co.", "tagline": "Gear for every trail", "assistant_name": "Scout"},
    StoreId.STORE_B: {"name": "Bloom & Brew", "tagline": "Coffee, tea & a cozier kitchen", "assistant_name": "Maple"},
}

ORDER_PREFIX: dict[StoreId, str] = {StoreId.STORE_A: "SA-", StoreId.STORE_B: "BB-"}

US_REGIONS = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK "
    "OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)
# Regions each store does not ship to (Store A's policy: contiguous US only).
SHIPPING_EXCLUDED_REGIONS: dict[StoreId, frozenset[str]] = {
    StoreId.STORE_A: frozenset({"AK", "HI"}),
    StoreId.STORE_B: frozenset(),
}

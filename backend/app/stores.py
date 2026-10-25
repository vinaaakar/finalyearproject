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

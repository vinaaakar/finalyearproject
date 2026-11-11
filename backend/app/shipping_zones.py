"""Shipping rates per destination country (country-aware checkout).

- United States: the store's existing rates (`store_profile`: standard, free-shipping minimum, expedited) — unchanged.
- Any other country (India today): ONLY zones the owner has configured in `<SHIPPING_CONFIG_DIR>/<store>.json`
  (default `config/shipping/`; no such file exists yet). Without one, the destination has NO rates: checkout says that
  shipping needs confirmation and refuses to place the order. US prices, US delivery promises and US free-shipping
  thresholds are never applied to another country, and no fee, partner or delivery time is invented.

File format (amounts in minor units of the zone's `currency`, which must be the destination's currency — INR for
India, app/pricing.py; one entry per zone):
    {"IN": [{"name": "Tamil Nadu", "currency": "INR", "regions": ["TN", "PY"], "standard_cents": 0, "expedited_cents": null,
             "free_over_cents": null, "eta_min_days": 3, "eta_max_days": 6},
            {"name": "Chennai", "currency": "INR", "pin_prefixes": ["600"], "standard_cents": 0, "eta_min_days": 2, "eta_max_days": 3}]}
A zone is chosen by the longest matching PIN prefix, then by state / union territory (app/markets.shipping_zone).
"""

from __future__ import annotations

import dataclasses
import json
import logging
from pathlib import Path
from typing import Any

from . import repositories as repo
from .markets import MARKETS, shipping_zone
from .pricing import CURRENCY_BY_COUNTRY
from .stores import StoreId

log = logging.getLogger("app.shipping")
_REQUIRED = {"name": str, "standard_cents": int}
_KNOWN = {"name", "currency", "regions", "pin_prefixes", "standard_cents", "expedited_cents", "free_over_cents",
          "eta_min_days", "eta_max_days"}


def _valid_zone(z: Any, currency: str | None = None) -> bool:
    if not isinstance(z, dict) or z.get("currency") != currency or any(not isinstance(z.get(k), t) for k, t in _REQUIRED.items()):
        return False
    if set(z) - _KNOWN or not (z.get("regions") or z.get("pin_prefixes")) or z["standard_cents"] < 0:
        return False      # unknown keys are refused: a typo must not silently drop a rule
    # A delivery time is optional (never invented); when given, both bounds are needed.
    eta = (z.get("eta_min_days"), z.get("eta_max_days"))
    if eta != (None, None) and not (all(isinstance(v, int) for v in eta) and 0 <= eta[0] <= eta[1]):
        return False
    return all(z.get(k) is None or (isinstance(z[k], int) and z[k] >= 0) for k in ("expedited_cents", "free_over_cents"))


def load_zones(config_dir: Path, store: StoreId, country: str) -> list[dict[str, Any]]:
    """Zones the owner configured for `country`; [] if none (an invalid file is refused as a whole and logged)."""
    path = Path(config_dir) / f"{store.value}.json"
    if not path.is_file():
        return []
    try:
        zones = json.loads(path.read_text()).get(country, [])
    except (OSError, ValueError, AttributeError):
        log.error("shipping config unreadable store=%s", store.value)
        return []
    if not isinstance(zones, list) or not all(_valid_zone(z, CURRENCY_BY_COUNTRY.get(country)) for z in zones):
        log.error("shipping config invalid store=%s country=%s; destination treated as not configured", store.value, country)
        return []
    return zones


def rates_for(store: StoreId, config_dir: Path, country: str = "US", region: str | None = None,
              postal_code: str | None = None) -> dict[str, Any] | None:
    """Rates for a destination, shaped like repo.get_shipping_rates; None = no rates for this destination (yet)."""
    base = repo.get_shipping_rates(store)
    if country == "US":
        return {**base, "country": "US", "expedited_label": "Expedited (2-day)"}
    zones = load_zones(config_dir, store, country)
    if not zones or not region or not postal_code:
        return None
    zone = shipping_zone(dataclasses.replace(MARKETS[country], shipping_zones=tuple(zones)), region.upper(), postal_code)
    if zone is None:
        return None
    eta = f"{zone['eta_min_days']}–{zone['eta_max_days']} days" if zone.get("eta_min_days") is not None else None
    return {**base, "currency": zone["currency"], "country": country, "standard_shipping_cents": zone["standard_cents"],
            "free_shipping_min_cents": zone.get("free_over_cents"), "expedited_shipping_cents": zone.get("expedited_cents"),
            "standard_label": f"Standard ({eta})" if eta else "Standard delivery", "expedited_label": "Expedited", "zone": zone["name"]}


def configured(store: StoreId, config_dir: Path, country: str) -> bool:
    return country == "US" or bool(load_zones(config_dir, store, country))

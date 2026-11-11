"""Phase I: market configuration — Indian addresses, PIN codes, mobile numbers, shipping zones, INR formatting, and the
guard that keeps an India store from running on USD prices. No price, fee or delivery time is invented anywhere."""

from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from app import markets as mk
from app.config import load_settings
from app.main import create_app

from .conftest import db_exec

IN = mk.MARKETS["IN"]
GOOD = {"full_name": "Priya R", "line1": "12 Anna Salai", "city": "Chennai", "region": "TN", "postal_code": "600002",
        "country": "IN", "phone": "+91 98765 43210"}


def test_india_has_all_36_states_and_union_territories():
    kinds = [k for _, _, k in mk.IN_REGIONS]
    assert kinds.count("state") == 28 and kinds.count("union_territory") == 8
    assert len({c for c, _, _ in mk.IN_REGIONS}) == 36
    assert ("TN", "Tamil Nadu", "state") in mk.IN_REGIONS and ("PY", "Puducherry", "union_territory") in mk.IN_REGIONS


def test_valid_indian_address_is_normalised():
    out = mk.validate_address(IN, {**GOOD, "region": "tn"})
    assert out["region"] == "TN" and out["phone"] == "+919876543210" and out["country"] == "IN"
    for typed in ("9876543210", "98765-43210", "+91-98765 43210", "(+91) 98765 43210"):
        assert mk.validate_address(IN, {**GOOD, "phone": typed})["phone"] == "+919876543210"


@pytest.mark.parametrize("field, value", [
    ("postal_code", "060002"), ("postal_code", "60002"), ("postal_code", "6000021"), ("postal_code", "6000 02"),
    ("region", "CA"), ("region", "XX"), ("phone", "12345 67890"), ("phone", "98765"), ("phone", ""), ("country", "US")])
def test_invalid_indian_address_is_refused_with_the_field(field, value):
    with pytest.raises(mk.AddressError) as e:
        mk.validate_address(IN, {**GOOD, field: value})
    assert any(p["field"] == f"shipping.{field}" for p in e.value.problems)


def test_us_market_keeps_todays_rules():
    us = mk.MARKETS["US"]
    a = {"full_name": "T", "line1": "1 Trail Way", "city": "Boulder", "region": "CO", "postal_code": "80302-1234"}
    assert mk.validate_address(us, a)["country"] == "US"
    with pytest.raises(mk.AddressError):
        mk.validate_address(us, {**a, "postal_code": "8030"})
    # Country-aware checkout: US keeps its fields; a phone (+1) may be given but is not required.
    assert us.public()["phone"]["required"] is False and us.public()["phone"]["dial_code"] == "+1" and len(us.public()["regions"]) == 51


def test_shipping_zones_resolve_by_longest_pin_prefix_then_state():
    m = dataclasses.replace(IN, shipping_zones=(
        {"name": "Chennai metro", "pin_prefixes": ["600"]}, {"name": "Chennai central", "pin_prefixes": ["6000"]},
        {"name": "Tamil Nadu", "regions": ["TN", "PY"]}))
    assert mk.shipping_zone(m, "TN", "600002")["name"] == "Chennai central"
    assert mk.shipping_zone(m, "TN", "600100")["name"] == "Chennai metro"
    assert mk.shipping_zone(m, "TN", "641001")["name"] == "Tamil Nadu"
    assert mk.shipping_zone(m, "KA", "560001") is None                     # not deliverable
    assert mk.shipping_zone(IN, "TN", "600002") is None                    # nothing configured → nothing invented


def test_india_market_reports_delivery_not_configured():
    assert IN.public()["shipping_configured"] is False
    assert IN.public()["currency"] == "INR" and IN.public()["phone"]["required"] is True


@pytest.mark.parametrize("minor, currency, text", [
    (12499900, "INR", "₹1,24,999.00"), (99, "INR", "₹0.99"), (100000, "INR", "₹1,000.00"), (12345678901, "INR", "₹12,34,56,789.01"),
    (124999, "USD", "$1,249.99"), (4595, "USD", "$45.95"), (-500, "USD", "-$5.00")])
def test_money_formatting(minor, currency, text):
    assert mk.format_money(minor, currency) == text


def test_market_endpoint_matches_the_store_configuration(client):
    m = client.get("/api/stores/store-a/market").json()["market"]
    assert m["code"] == "US" and m["currency"] == "USD" and m["postal_label"] == "ZIP code" and m["shipping_configured"]
    assert {r["code"] for r in m["regions"]} >= {"CO", "IL", "AK"}


def test_market_setting_is_validated():
    base = {"APP_ENV": "development", "APP_SECRET_KEY": "x" * 48, "STORE_A_DATABASE_URL": "postgresql://u:p@h/a",
            "STORE_B_DATABASE_URL": "postgresql://u:p@h/b"}
    from pathlib import Path
    india_only = load_settings(env=base, env_file=Path("/nonexistent"))           # this project's default: India only
    assert india_only.store_markets == {"store-a": "IN", "store-b": "IN"} and india_only.checkout_countries == ("IN",)
    mixed = load_settings(env={**base, "STORE_A_MARKET": "us"}, env_file=Path("/nonexistent"))
    assert mixed.store_markets == {"store-a": "US", "store-b": "IN"} and mixed.checkout_countries == ("IN", "US")
    from app.config import ConfigError
    with pytest.raises(ConfigError):
        load_settings(env={**base, "STORE_A_MARKET": "FR"}, env_file=Path("/nonexistent"))


def test_india_store_without_inr_prices_starts_but_reports_and_never_shows_usd(settings):
    """An India store's prices come only from the approved INR list (never converted). Without one, the API still starts,
    health reports the gap, and products show no price at all — never the USD catalogue amount."""
    app = create_app(dataclasses.replace(settings, store_markets={"store-a": "IN", "store-b": "US"}), llm=False)
    with TestClient(app) as c:
        selling = c.get("/api/health").json()["selling"]
        assert selling["store-a"] == {"market": "IN", "currency": "INR", "products": 10, "priced": 0, "prices_complete": False,
                                      "shipping_configured": False}
        assert selling["store-b"]["currency"] == "USD" and selling["store-b"]["prices_complete"]
        p = c.get("/api/stores/store-a/products/lumen-300-headlamp").json()["product"]
        assert p["price"] is None and p["price_cents"] is None and p["currency"] == "INR" and p["prices"] == {"INR": None}


def test_india_store_with_inr_catalogue_starts_and_publishes_indian_rules(settings):
    db_exec(settings, "store-b", "UPDATE store_profile SET currency = 'INR'")
    try:
        app = create_app(dataclasses.replace(settings, store_markets={"store-a": "US", "store-b": "IN"}), llm=False)
        with TestClient(app) as c:
            m = c.get("/api/stores/store-b/market").json()["market"]
            assert m["code"] == "IN" and m["postal_pattern"] == r"^[1-9][0-9]{5}$" and m["line2_label"] == "Address line 2 / Landmark (optional)"
            assert m["shipping_configured"] is False
    finally:
        db_exec(settings, "store-b", "UPDATE store_profile SET currency = 'USD'")

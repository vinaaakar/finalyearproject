"""Country-aware checkout (both stores): India and United States addresses, PIN/ZIP validation, phone numbers,
destination-specific shipping (US rates never applied to India), currency by destination (INR only from owner-approved
prices, never converted from USD), order persistence, store isolation."""

from __future__ import annotations

import dataclasses
import json

import pytest

from app.seed import AGENT_PASSWORD, DEMO_PASSWORDS
from app.stores import StoreId

from app.markets import format_money

from .conftest import ADDRESS_A, AGENT_A, AGENT_B, JORDAN, db_exec, idem, login, make_client, new_customer, set_stock

SLUG = {"store-a": "lumen-300-headlamp", "store-b": "wildflower-honey"}
CUMBUM = {"full_name": "Priya Raman", "line1": "12 Kambam Main Road", "line2": "Near the bus stand", "city": "Cumbum",
          "region": "TN", "postal_code": "625521", "country": "IN", "phone": "+91 98765 43210"}
ZONES = {"IN": [{"name": "Tamil Nadu", "currency": "INR", "regions": ["TN", "PY"], "standard_cents": 12000, "expedited_cents": None,
                 "free_over_cents": None, "eta_min_days": 4, "eta_max_days": 7}]}   # TEST DATA ONLY, not a real rate
# TEST DATA ONLY: "approved" INR prices in paise. Deliberately unrelated to the USD prices, so any conversion would show.
INR_TEST_PRICES = {"store-a": {"lumen-300-headlamp": 199900, "trailhead-55l-backpack": 1500000},
                   "store-b": {"wildflower-honey": 45000}}


def _customer(client, store):
    set_stock(client.app.state.settings, store, SLUG[store], 60)
    h, _ = new_customer(client, store)
    client.post(f"/api/stores/{store}/cart/items", json={"slug": SLUG[store], "quantity": 1}, headers=h)
    return h


def _quote(client, store, h, **destination):
    return client.post(f"/api/stores/{store}/checkout/quote", headers=h,
                       json={"shipping_method": "standard", **({"destination": destination} if destination else {})}).json()["cart"]


def _approve_inr(settings, store, prices):
    for slug, paise in prices.items():
        db_exec(settings, store, "INSERT INTO product_prices (product_id, currency, price_minor, approved_by) "
                "SELECT id, 'INR', %s, 'test fixture' FROM products WHERE slug = %s "
                "ON CONFLICT (product_id, currency) DO UPDATE SET price_minor = EXCLUDED.price_minor", [paise, slug])


@pytest.fixture
def inr_prices(settings):
    """TEST databases only: approve the INR test prices, and remove them again afterwards."""
    for store, prices in INR_TEST_PRICES.items():
        _approve_inr(settings, store, prices)
    yield
    for store in INR_TEST_PRICES:
        db_exec(settings, store, "DELETE FROM product_prices WHERE approved_by = 'test fixture'")


@pytest.fixture
def zones_client(settings, tmp_path):
    for store in ("store-a", "store-b"):
        (tmp_path / f"{store}.json").write_text(json.dumps(ZONES))
    with make_client(settings, shipping_config_dir=tmp_path) as c:
        yield c


# ---- address options ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_address_options_offer_india_and_us_with_their_own_rules(client, store):
    h = _customer(client, store)
    d = client.get(f"/api/stores/{store}/checkout/address-options", headers=h).json()
    by = {c["code"]: c for c in d["countries"]}
    assert set(by) == {"IN", "US"} and d["default_country"] == "IN"            # a new customer: India
    india, us = by["IN"], by["US"]
    names = {r["name"] for r in india["regions"]}
    assert len(india["regions"]) == 36 and "Tamil Nadu" in names and "Puducherry" in names and "Alabama" not in names
    assert india["postal_label"] == "PIN code" and india["phone"]["required"] and india["phone"]["dial_code"] == "+91"
    assert india["shipping_configured"] is False                              # no India rates exist yet
    assert india["currency"] == "INR" and india["prices_configured"] is False  # and no approved INR prices
    assert us["currency"] == "USD" and us["prices_configured"] is True
    assert len(us["regions"]) == 51 and "District of Columbia" in {r["name"] for r in us["regions"]} and "Tamil Nadu" not in {r["name"] for r in us["regions"]}
    assert us["postal_label"] == "ZIP code" and us["phone"]["required"] is False and us["shipping_configured"]


def test_returning_us_customer_defaults_to_us(client):
    h = login(client, "store-a", JORDAN, DEMO_PASSWORDS[StoreId.STORE_A])       # seeded orders in Portland, OR
    assert client.get("/api/stores/store-a/checkout/address-options", headers=h).json()["default_country"] == "US"


# ---- shipping for India without configured rates -------------------------------------------------------------------------
@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_india_without_prices_or_rates_shows_no_usd_amounts_at_all(client, store):
    """Today's real situation: no approved INR prices and no India rates. Nothing in USD is shown or charged for India."""
    h = _customer(client, store)
    us = _quote(client, store, h)
    india = _quote(client, store, h, country="IN", region="TN", postal_code="625521")
    assert us["shipping_available"] and us["shipping_options"] and us["currency"] == "USD" and us["subtotal"].startswith("$")
    assert india["currency"] == "INR" and india["prices_available"] is False and "Prices in INR haven't been set" in india["price_problem"]
    assert india["subtotal_cents"] is None and india["total_cents"] is None and india["subtotal"] is None and india["total"] is None
    assert all(i["unit_price"] is None and i["line_total"] is None for i in india["items"])
    assert india["shipping_available"] is False and india["shipping_options"] == [] and india["shipping"] is None
    assert india["can_checkout"] is False
    assert "$" not in json.dumps(india) and "Expedited (2-day)" not in json.dumps(india)


@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_india_with_approved_prices_but_no_rates(client, store, inr_prices):
    h = _customer(client, store)
    india = _quote(client, store, h, country="IN", region="TN", postal_code="625521")
    paise = INR_TEST_PRICES[store][SLUG[store]]
    assert india["prices_available"] and india["subtotal_cents"] == paise and india["subtotal"].startswith("₹")
    assert india["shipping_available"] is False and india["shipping_options"] == [] and india["can_checkout"] is False
    assert india["total_cents"] == india["subtotal_cents"] and india["total_excludes_shipping"]
    assert "hasn't set delivery rates" in india["shipping_problem"] and "$" not in json.dumps(india)


@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_india_order_is_refused_without_rates_and_nothing_is_created(client, store):
    h = _customer(client, store)
    before = db_exec(client.app.state.settings, store, "SELECT count(*) FROM orders")[0][0]
    r = client.post(f"/api/stores/{store}/checkout", headers={**h, **idem()},
                    json={"shipping": CUMBUM, "expected_total_cents": _quote(client, store, h)["subtotal_cents"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "shipping_not_configured"
    assert db_exec(client.app.state.settings, store, "SELECT count(*) FROM orders")[0][0] == before
    assert client.get(f"/api/stores/{store}/cart", headers=h).json()["cart"]["item_count"] == 1     # cart kept


# ---- India validation ----------------------------------------------------------------------------------------------------
def test_india_order_is_refused_without_approved_prices_even_with_rates(zones_client, store="store-a"):
    c = zones_client
    h = _customer(c, store)
    q = _quote(c, store, h, country="IN", region="TN", postal_code="625521")
    assert q["shipping_available"] and q["shipping_options"] == [] and q["prices_available"] is False and q["total_cents"] is None
    before = db_exec(c.app.state.settings, store, "SELECT count(*) FROM orders")[0][0]
    usd_total = _quote(c, store, h)["total_cents"]                       # a client replaying the USD total gets nowhere
    r = c.post(f"/api/stores/{store}/checkout", headers={**h, **idem()}, json={"shipping": CUMBUM, "expected_total_cents": usd_total})
    assert r.status_code == 409 and r.json()["error"]["code"] == "price_not_configured"
    assert db_exec(c.app.state.settings, store, "SELECT count(*) FROM orders")[0][0] == before


@pytest.mark.parametrize("override, field", [
    ({"postal_code": "62552"}, "shipping.postal_code"), ({"postal_code": "6255211"}, None), ({"postal_code": "025521"}, "shipping.postal_code"),
    ({"region": "CO"}, "shipping.region"), ({"region": "XX"}, "shipping.region"), ({"phone": None}, "shipping.phone"),
    ({"phone": "12345"}, None), ({"phone": "+1 303 555 0100"}, "shipping.phone")])
def test_india_address_validation(zones_client, inr_prices, override, field):
    h = _customer(zones_client, "store-a")
    total = _quote(zones_client, "store-a", h, country="IN", region="TN", postal_code="625521")["total_cents"]
    r = zones_client.post("/api/stores/store-a/checkout", headers={**h, **idem()}, json={"shipping": {**CUMBUM, **override}, "expected_total_cents": total})
    assert r.status_code == 422, r.text
    if field:
        assert field in json.dumps(r.json()["error"].get("details"))


def test_us_address_with_indian_pin_is_rejected(client):
    h = _customer(client, "store-a")
    r = client.post("/api/stores/store-a/checkout", headers={**h, **idem()},
                    json={"shipping": {**ADDRESS_A, "postal_code": "625521"}, "expected_total_cents": 4595})
    assert r.status_code == 422


# ---- India with configured (test) rates: full order -----------------------------------------------------------------------
@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_india_order_persists_country_address_phone_and_inr(zones_client, inr_prices, store):
    c = zones_client
    h = _customer(c, store)
    q = _quote(c, store, h, country="IN", region="TN", postal_code="625521")
    paise = INR_TEST_PRICES[store][SLUG[store]]
    assert q["shipping_available"] and [o["label"] for o in q["shipping_options"]] == ["Standard (4–7 days)"]   # zone's own terms only
    assert q["currency"] == "INR" and q["subtotal_cents"] == paise                                             # approved price, not converted
    assert q["shipping_cents"] == 12000 and q["total_cents"] == paise + 12000 and q["can_checkout"]
    assert q["shipping_options"][0]["price"] == "₹120.00" and q["shipping"] == "₹120.00" and "$" not in json.dumps(q)
    r = c.post(f"/api/stores/{store}/checkout", headers={**h, **idem()}, json={"shipping": CUMBUM, "expected_total_cents": q["total_cents"]})
    assert r.status_code == 201, r.text
    number = r.json()["order"]["order_number"]
    try:
        o = c.get(f"/api/stores/{store}/orders/{number}", headers=h).json()["order"]
        assert o["shipping_address"] == {"name": "Priya Raman", "line1": "12 Kambam Main Road", "line2": "Near the bus stand",
                                         "city": "Cumbum", "region": "TN", "postal_code": "625521", "country": "IN",
                                         "country_name": "India", "phone": "+919876543210"}
        assert o["currency"] == "INR" and o["shipping"] == "₹120.00" and o["total"].startswith("₹")
        assert o["items"][0]["unit_price"] == format_money(paise, "INR")
        row = db_exec(c.app.state.settings, store, "SELECT currency, total_cents FROM orders WHERE order_number = %s", [number])[0]
        assert row == ("INR", paise + 12000)
        pay = c.post(f"/api/stores/{store}/orders/{number}/payments", headers=h)
        assert pay.status_code == 200 and pay.json()["payment"]["amount"] == format_money(paise + 12000, "INR")
        assert db_exec(c.app.state.settings, store, "SELECT p.currency FROM payments p JOIN orders o ON o.id = p.order_id "
                       "WHERE o.order_number = %s", [number])[0][0] == "INR"
        agent = login(c, store, AGENT_A if store == "store-a" else AGENT_B, AGENT_PASSWORD)
        staff = c.get(f"/api/stores/{store}/staff/orders/{number}", headers=agent).json()["order"]
        assert staff["shipping_address"]["country"] == "IN" and staff["shipping_address"]["phone"] == "+919876543210"
        assert staff["total"] == o["total"] and staff["currency"] == "INR"
        listed = c.get(f"/api/stores/{store}/staff/orders?q={number}", headers=agent).json()["orders"]
        assert [x["total"] for x in listed] == [o["total"]]
        other = "store-b" if store == "store-a" else "store-a"
        other_agent = login(c, other, AGENT_B if other == "store-b" else AGENT_A, AGENT_PASSWORD)
        assert c.get(f"/api/stores/{other}/staff/orders/{number}", headers=other_agent).status_code == 404   # never in the other store
        assert c.get(f"/api/stores/{store}/checkout/address-options", headers=h).json()["default_country"] == "IN"
    finally:
        c.post(f"/api/stores/{store}/orders/{number}/cancel", headers=h)


def test_zone_terms_never_borrow_us_free_shipping(zones_client, inr_prices):
    """Store A's US free-shipping threshold ($75) must not apply to India: the pack still pays the zone fee."""
    c = zones_client
    set_stock(c.app.state.settings, "store-a", "trailhead-55l-backpack", 30)
    h, _ = new_customer(c, "store-a")
    c.post("/api/stores/store-a/cart/items", json={"slug": "trailhead-55l-backpack", "quantity": 1}, headers=h)
    assert _quote(c, "store-a", h)["shipping_cents"] == 0                                  # US: free over $75
    assert _quote(c, "store-a", h, country="IN", region="TN", postal_code="625521")["shipping_cents"] == 12000


def test_unconfigured_state_has_no_rates_even_with_a_zone_file(zones_client):
    h = _customer(zones_client, "store-a")
    q = _quote(zones_client, "store-a", h, country="IN", region="KA", postal_code="560001")    # Bengaluru: no zone
    assert q["shipping_available"] is False and q["shipping_options"] == []


@pytest.mark.parametrize("zone", [{"name": "Broken", "regions": ["TN"]},
                                  {**ZONES["IN"][0], "currency": "USD"},          # a USD fee is never applied to India
                                  {k: v for k, v in ZONES["IN"][0].items() if k != "currency"}])
def test_invalid_zone_file_counts_as_not_configured(settings, tmp_path, zone):
    (tmp_path / "store-a.json").write_text(json.dumps({"IN": [zone]}))
    with make_client(settings, shipping_config_dir=tmp_path) as c:
        h = _customer(c, "store-a")
        assert _quote(c, "store-a", h, country="IN", region="TN", postal_code="625521")["shipping_available"] is False


# ---- currency in the catalogue and cart ----------------------------------------------------------------------------------
@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_cart_in_delivery_country_currency(client, store):
    h = _customer(client, store)
    plain = client.get(f"/api/stores/{store}/cart", headers=h).json()["cart"]
    us = client.get(f"/api/stores/{store}/cart?country=US", headers=h).json()["cart"]
    india = client.get(f"/api/stores/{store}/cart?country=IN", headers=h).json()["cart"]
    assert plain["currency"] == us["currency"] == "USD" and plain["total_cents"] == us["total_cents"] and plain["shipping_options"] == us["shipping_options"]
    assert india["currency"] == "INR" and india["prices_available"] is False and india["total"] is None and "$" not in json.dumps(india)
    assert client.get(f"/api/stores/{store}/cart?country=FR", headers=h).status_code == 422


# ---- US regression -------------------------------------------------------------------------------------------------------
def test_us_checkout_unchanged_and_optional_phone_is_stored(client):
    h = _customer(client, "store-a")
    legacy = _quote(client, "store-a", h)
    explicit = _quote(client, "store-a", h, country="US", region="CO", postal_code="80302")
    for k in ("shipping_cents", "total_cents", "shipping_options"):
        assert legacy[k] == explicit[k]
    assert [o["label"] for o in legacy["shipping_options"]] == ["Standard", "Expedited (2-day)"]
    r = client.post("/api/stores/store-a/checkout", headers={**h, **idem()},
                    json={"shipping": {**ADDRESS_A, "postal_code": "80302-1234", "phone": "(303) 555-0100"}, "expected_total_cents": legacy["total_cents"]})
    assert r.status_code == 201, r.text
    number = r.json()["order"]["order_number"]
    o = client.get(f"/api/stores/store-a/orders/{number}", headers=h).json()["order"]
    assert o["shipping_address"]["country"] == "US" and o["shipping_address"]["phone"] == "+13035550100"
    assert o["shipping_address"]["postal_code"] == "80302-1234" and o["currency"] == "USD" and o["total"].startswith("$")
    client.post(f"/api/stores/store-a/orders/{number}/cancel", headers=h)

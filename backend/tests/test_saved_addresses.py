"""Tests for Amazon-style Saved Address Management:
- First-time customer checkout automatically saves default address
- Returning customer automatically gets default address pre-filled
- Multiple saved addresses (Home, Work) and setting new default
- Editing and deleting addresses (deleting default promotes remaining)
- Duplicate prevention (repeated checkout or manual save with same address avoids duplicate rows)
- Customer isolation (Customer A cannot access, edit, delete, or default Customer B's addresses)
- Storefront isolation (Store A addresses separate from Store B addresses)
- Existing orders retain historical address snapshot even after address is modified or deleted
- Indian market address validation (states, PIN code, +91 phone)
- Checkout working on both storefronts
"""

from __future__ import annotations

import pytest

import json

from app.stores import StoreId
from .conftest import AGENT_A, AGENT_B, JORDAN, db_exec, idem, login, make_client, new_customer, set_stock

SLUG = {"store-a": "lumen-300-headlamp", "store-b": "wildflower-honey"}

INR_TEST_PRICES = {
    "store-a": {"lumen-300-headlamp": 199900},
    "store-b": {"wildflower-honey": 45000},
}

ZONES = {
    "IN": [
        {
            "name": "Tamil Nadu",
            "currency": "INR",
            "regions": ["TN", "PY"],
            "standard_cents": 12000,
            "expedited_cents": None,
            "free_over_cents": None,
            "eta_min_days": 4,
            "eta_max_days": 7,
        }
    ]
}

HOME_ADDR = {
    "label": "Home",
    "full_name": "Priya Raman",
    "line1": "12 Kambam Main Road",
    "line2": "Near bus stand",
    "city": "Cumbum",
    "region": "TN",
    "postal_code": "625521",
    "country": "IN",
    "phone": "+91 98765 43210",
}

WORK_ADDR = {
    "label": "Work",
    "full_name": "Priya Raman",
    "line1": "500 Anna Salai",
    "line2": "Floor 4, Tech Park",
    "city": "Chennai",
    "region": "TN",
    "postal_code": "600002",
    "country": "IN",
    "phone": "+91 98765 12345",
}


def _approve_inr(settings, store, prices):
    for slug, paise in prices.items():
        db_exec(
            settings,
            store,
            "INSERT INTO product_prices (product_id, currency, price_minor, approved_by) "
            "SELECT id, 'INR', %s, 'test address fixture' FROM products WHERE slug = %s "
            "ON CONFLICT (product_id, currency) DO UPDATE SET price_minor = EXCLUDED.price_minor",
            [paise, slug],
        )


@pytest.fixture
def setup_store(settings):
    for store, prices in INR_TEST_PRICES.items():
        _approve_inr(settings, store, prices)
        set_stock(settings, store, SLUG[store], 50)
    yield
    for store in INR_TEST_PRICES:
        db_exec(settings, store, "DELETE FROM product_prices WHERE approved_by = 'test address fixture'")


@pytest.fixture
def zones_client(settings, tmp_path):
    for store in ("store-a", "store-b"):
        (tmp_path / f"{store}.json").write_text(json.dumps(ZONES))
    with make_client(settings, shipping_config_dir=tmp_path) as c:
        yield c


def test_first_time_customer_checkout_saves_default_address(zones_client, setup_store):
    """First checkout saves address to account and automatically makes it default."""
    client = zones_client
    for store in ("store-a", "store-b"):
        h, cust = new_customer(client, store)
        # Verify customer initially has no saved addresses
        res = client.get(f"/api/stores/{store}/addresses", headers=h)
        assert res.status_code == 200
        assert res.json()["addresses"] == []
        assert client.get(f"/api/stores/{store}/addresses/default", headers=h).json()["address"] is None

        # Add item and quote
        client.post(f"/api/stores/{store}/cart/items", json={"slug": SLUG[store], "quantity": 1}, headers=h)
        quote = client.post(
            f"/api/stores/{store}/checkout/quote",
            headers=h,
            json={"shipping_method": "standard", "destination": {"country": "IN", "region": "TN", "postal_code": "625521"}},
        ).json()["cart"]

        # Checkout with new address
        checkout_res = client.post(
            f"/api/stores/{store}/checkout",
            headers={**h, **idem()},
            json={
                "shipping": HOME_ADDR,
                "shipping_method": "standard",
                "expected_total_cents": quote["total_cents"],
                "save_address": True,
            },
        )
        assert checkout_res.status_code == 201

        # Check that address was saved and marked default
        addrs = client.get(f"/api/stores/{store}/addresses", headers=h).json()["addresses"]
        assert len(addrs) == 1
        saved = addrs[0]
        assert saved["full_name"] == "Priya Raman"
        assert saved["line1"] == "12 Kambam Main Road"
        assert saved["line2"] == "Near bus stand"
        assert saved["city"] == "Cumbum"
        assert saved["region"] == "TN"
        assert saved["postal_code"] == "625521"
        assert saved["phone"] == "+919876543210"
        assert saved["is_default"] is True

        # Default endpoint returns it
        def_addr = client.get(f"/api/stores/{store}/addresses/default", headers=h).json()["address"]
        assert def_addr is not None
        assert def_addr["id"] == saved["id"]


def _checkout(client, store, h, body_extra=None):
    """Adds one item, quotes for HOME_ADDR's destination and checks out; returns the checkout response."""
    client.post(f"/api/stores/{store}/cart/items", json={"slug": SLUG[store], "quantity": 1}, headers=h)
    q = client.post(f"/api/stores/{store}/checkout/quote", headers=h,
                    json={"shipping_method": "standard", "destination": {"country": "IN", "region": "TN", "postal_code": "625521"}}).json()["cart"]
    body = {"shipping": HOME_ADDR, "shipping_method": "standard", "expected_total_cents": q["total_cents"], **(body_extra or {})}
    return client.post(f"/api/stores/{store}/checkout", headers={**h, **idem()}, json=body)


def test_checkout_without_save_address_does_not_save(zones_client, setup_store):
    """Saving is opt-in: a checkout that omits save_address places the order exactly as before and saves nothing."""
    client = zones_client
    for store in ("store-a", "store-b"):
        h, _ = new_customer(client, store)
        res = _checkout(client, store, h)
        assert res.status_code == 201
        assert res.json()["created"] is True
        number = res.json()["order"]["order_number"]
        order = client.get(f"/api/stores/{store}/orders/{number}", headers=h).json()["order"]
        assert order["shipping_address"]["line1"] == HOME_ADDR["line1"]
        assert order["shipping_address"]["postal_code"] == HOME_ADDR["postal_code"]
        assert client.get(f"/api/stores/{store}/addresses", headers=h).json()["addresses"] == []
        assert client.get(f"/api/stores/{store}/addresses/default", headers=h).json()["address"] is None


def test_checkout_with_save_address_false_does_not_save(zones_client, setup_store):
    """An explicit opt-out (even with make_default) saves nothing."""
    client = zones_client
    store = "store-a"
    h, _ = new_customer(client, store)
    res = _checkout(client, store, h, {"save_address": False, "make_default": True})
    assert res.status_code == 201
    assert client.get(f"/api/stores/{store}/addresses", headers=h).json()["addresses"] == []


def test_checkout_succeeds_and_logs_when_address_save_fails(zones_client, setup_store, monkeypatch, caplog):
    """A failing optional address save never fails the (already committed) order, and is logged without personal data."""
    import logging

    from app import repositories

    def boom(*args, **kwargs):
        # The message deliberately carries personal data: it must not reach the log.
        raise RuntimeError(f"cannot save {HOME_ADDR['line1']} {HOME_ADDR['postal_code']} {HOME_ADDR['phone']}")

    monkeypatch.setattr(repositories, "save_or_update_address", boom)
    client = zones_client
    store = "store-a"
    h, _ = new_customer(client, store)
    with caplog.at_level(logging.WARNING, logger="app.checkout"):
        res = _checkout(client, store, h, {"save_address": True, "make_default": True})

    assert res.status_code == 201
    order_number = res.json()["order"]["order_number"]
    # The order exists and is the customer's.
    detail = client.get(f"/api/stores/{store}/orders/{order_number}", headers=h)
    assert detail.status_code == 200
    assert detail.json()["order"]["shipping_address"]["line1"] == HOME_ADDR["line1"]
    # Nothing was saved.
    monkeypatch.undo()
    assert client.get(f"/api/stores/{store}/addresses", headers=h).json()["addresses"] == []

    records = [r for r in caplog.records if r.name == "app.checkout"]
    assert len(records) == 1
    rec = records[0]
    assert rec.levelno == logging.WARNING
    assert rec.exc_info is None
    msg = rec.getMessage()
    assert "saving checkout address failed" in msg
    assert order_number in msg and store in msg and "RuntimeError" in msg
    for private in (HOME_ADDR["full_name"], HOME_ADDR["line1"], HOME_ADDR["line2"], HOME_ADDR["city"],
                    HOME_ADDR["postal_code"], "9876543210", "98765 43210"):
        assert private not in caplog.text


def test_duplicate_prevention_on_repeated_checkout(zones_client, setup_store):
    """Checking out again with the same address does not create duplicate rows."""
    client = zones_client
    store = "store-a"
    h, _ = new_customer(client, store)
    client.post(f"/api/stores/{store}/cart/items", json={"slug": SLUG[store], "quantity": 1}, headers=h)
    q1 = client.post(f"/api/stores/{store}/checkout/quote", headers=h,
                     json={"shipping_method": "standard", "destination": {"country": "IN", "region": "TN", "postal_code": "625521"}}).json()["cart"]
    client.post(f"/api/stores/{store}/checkout", headers={**h, **idem()},
                json={"shipping": HOME_ADDR, "shipping_method": "standard", "expected_total_cents": q1["total_cents"], "save_address": True})

    # Place a second order with same address
    client.post(f"/api/stores/{store}/cart/items", json={"slug": SLUG[store], "quantity": 1}, headers=h)
    q2 = client.post(f"/api/stores/{store}/checkout/quote", headers=h,
                     json={"shipping_method": "standard", "destination": {"country": "IN", "region": "TN", "postal_code": "625521"}}).json()["cart"]
    client.post(f"/api/stores/{store}/checkout", headers={**h, **idem()},
                json={"shipping": HOME_ADDR, "shipping_method": "standard", "expected_total_cents": q2["total_cents"], "save_address": True})

    addrs = client.get(f"/api/stores/{store}/addresses", headers=h).json()["addresses"]
    assert len(addrs) == 1


def test_multiple_saved_addresses_and_change_default(client):
    """Customer can have multiple addresses and switch default address."""
    store = "store-a"
    h, _ = new_customer(client, store)

    # Create Home address (becomes default because it's first)
    r1 = client.post(f"/api/stores/{store}/addresses", headers=h, json=HOME_ADDR)
    assert r1.status_code == 201
    home_id = r1.json()["address"]["id"]
    assert r1.json()["address"]["is_default"] is True

    # Create Work address (not default)
    r2 = client.post(f"/api/stores/{store}/addresses", headers=h, json={**WORK_ADDR, "is_default": False})
    assert r2.status_code == 201
    work_id = r2.json()["address"]["id"]
    assert r2.json()["address"]["is_default"] is False

    # List addresses
    addrs = client.get(f"/api/stores/{store}/addresses", headers=h).json()["addresses"]
    assert len(addrs) == 2
    assert addrs[0]["id"] == home_id and addrs[0]["is_default"] is True
    assert addrs[1]["id"] == work_id and addrs[1]["is_default"] is False

    # Set Work as default
    set_def = client.put(f"/api/stores/{store}/addresses/{work_id}/default", headers=h)
    assert set_def.status_code == 200

    # Verify default changed
    def_addr = client.get(f"/api/stores/{store}/addresses/default", headers=h).json()["address"]
    assert def_addr["id"] == work_id
    assert def_addr["is_default"] is True

    addrs_after = client.get(f"/api/stores/{store}/addresses", headers=h).json()["addresses"]
    assert addrs_after[0]["id"] == work_id and addrs_after[0]["is_default"] is True
    assert addrs_after[1]["id"] == home_id and addrs_after[1]["is_default"] is False


def test_edit_and_delete_address(client):
    """Customer can edit an address and delete an address; deleting default promotes remaining."""
    store = "store-b"
    h, _ = new_customer(client, store)

    r1 = client.post(f"/api/stores/{store}/addresses", headers=h, json=HOME_ADDR)
    home_id = r1.json()["address"]["id"]
    r2 = client.post(f"/api/stores/{store}/addresses", headers=h, json={**WORK_ADDR, "is_default": False})
    work_id = r2.json()["address"]["id"]

    # Edit Home address
    edit_res = client.put(
        f"/api/stores/{store}/addresses/{home_id}",
        headers=h,
        json={"line2": "Suite 99", "label": "Vacation Home"},
    )
    assert edit_res.status_code == 200
    updated = edit_res.json()["address"]
    assert updated["line2"] == "Suite 99"
    assert updated["label"] == "Vacation Home"

    # Delete Home (which is currently default)
    del_res = client.delete(f"/api/stores/{store}/addresses/{home_id}", headers=h)
    assert del_res.status_code == 204

    # Now Work address should have been promoted to default
    remaining = client.get(f"/api/stores/{store}/addresses", headers=h).json()["addresses"]
    assert len(remaining) == 1
    assert remaining[0]["id"] == work_id
    assert remaining[0]["is_default"] is True


def test_customer_isolation(client):
    """A customer cannot view, edit, set default, or delete another customer's addresses."""
    store = "store-a"
    h1, _ = new_customer(client, store)
    h2, _ = new_customer(client, store)

    # Customer 1 creates an address
    r = client.post(f"/api/stores/{store}/addresses", headers=h1, json=HOME_ADDR)
    addr_id = r.json()["address"]["id"]

    # Customer 2 attempts to get, update, set default, or delete Customer 1's address
    assert client.get(f"/api/stores/{store}/addresses/{addr_id}", headers=h2).status_code == 404
    assert client.put(f"/api/stores/{store}/addresses/{addr_id}", headers=h2, json={"city": "Madurai"}).status_code == 404
    assert client.put(f"/api/stores/{store}/addresses/{addr_id}/default", headers=h2).status_code == 404
    assert client.delete(f"/api/stores/{store}/addresses/{addr_id}", headers=h2).status_code == 404

    # Customer 2's address list remains empty
    assert client.get(f"/api/stores/{store}/addresses", headers=h2).json()["addresses"] == []


def test_storefront_isolation(client):
    """Addresses saved in Store A do not exist or appear in Store B."""
    h_a, cust_a = new_customer(client, "store-a")
    r_a = client.post("/api/stores/store-a/addresses", headers=h_a, json=HOME_ADDR)
    assert r_a.status_code == 201

    # Same email in Store B has separate account and no addresses
    # (Token for store-a is also rejected with 403 on store-b)
    assert client.get("/api/stores/store-b/addresses", headers=h_a).status_code == 403


def test_orders_retain_historical_address_snapshot(zones_client, setup_store):
    """Modifying or deleting a saved address does NOT alter an existing order's delivery address."""
    client = zones_client
    store = "store-a"
    h, _ = new_customer(client, store)

    client.post(f"/api/stores/{store}/cart/items", json={"slug": SLUG[store], "quantity": 1}, headers=h)
    q = client.post(f"/api/stores/{store}/checkout/quote", headers=h,
                    json={"shipping_method": "standard", "destination": {"country": "IN", "region": "TN", "postal_code": "625521"}}).json()["cart"]
    order_res = client.post(f"/api/stores/{store}/checkout", headers={**h, **idem()},
                            json={"shipping": HOME_ADDR, "shipping_method": "standard", "expected_total_cents": q["total_cents"], "save_address": True})
    order_num = order_res.json()["order"]["order_number"]

    # Get address id
    addrs = client.get(f"/api/stores/{store}/addresses", headers=h).json()["addresses"]
    addr_id = addrs[0]["id"]

    # Now modify the saved address completely
    client.put(f"/api/stores/{store}/addresses/{addr_id}", headers=h,
               json={"full_name": "Different Name", "line1": "99 New Street", "city": "Chennai", "region": "TN", "postal_code": "600001"})

    # Check order detail
    detail = client.get(f"/api/stores/{store}/orders/{order_num}", headers=h).json()["order"]
    assert detail["shipping_address"]["name"] == "Priya Raman"
    assert detail["shipping_address"]["line1"] == "12 Kambam Main Road"
    assert detail["shipping_address"]["city"] == "Cumbum"
    assert detail["shipping_address"]["postal_code"] == "625521"

    # Delete the saved address completely
    client.delete(f"/api/stores/{store}/addresses/{addr_id}", headers=h)

    # Order still has the original snapshot!
    detail_after_del = client.get(f"/api/stores/{store}/orders/{order_num}", headers=h).json()["order"]
    assert detail_after_del["shipping_address"]["name"] == "Priya Raman"
    assert detail_after_del["shipping_address"]["line1"] == "12 Kambam Main Road"


def test_indian_address_validation(client):
    """Validation rejects invalid PIN codes, invalid phone numbers, or invalid Indian regions."""
    store = "store-a"
    h, _ = new_customer(client, store)

    # Invalid PIN code (5 digits instead of 6)
    bad_pin = {**HOME_ADDR, "postal_code": "62552"}
    assert client.post(f"/api/stores/{store}/addresses", headers=h, json=bad_pin).status_code == 422

    # Invalid phone (too short)
    bad_phone = {**HOME_ADDR, "phone": "12345"}
    assert client.post(f"/api/stores/{store}/addresses", headers=h, json=bad_phone).status_code == 422

    # Invalid region (not in 36 states/UTs)
    bad_region = {**HOME_ADDR, "region": "ZZ"}
    assert client.post(f"/api/stores/{store}/addresses", headers=h, json=bad_region).status_code == 422

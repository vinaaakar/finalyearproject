"""Phase E: the order detail endpoint (customer order page) — ownership, store isolation, no internal identifiers."""

from __future__ import annotations

from app.seed import AGENT_PASSWORD, DEMO_PASSWORDS
from app.stores import StoreId

from .conftest import AGENT_A, ALEX, JORDAN, MARIA, login

PW_A, PW_B = DEMO_PASSWORDS[StoreId.STORE_A], DEMO_PASSWORDS[StoreId.STORE_B]
FORBIDDEN_KEYS = {"id", "customer_id", "product_id", "order_id", "password_hash", "email"}


def _keys(obj, out=None):
    out = set() if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            _keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _keys(v, out)
    return out


def test_owner_gets_items_prices_and_address(client):
    h = login(client, "store-a", ALEX, PW_A)
    r = client.get("/api/stores/store-a/orders/SA-10001", headers=h)
    assert r.status_code == 200
    o = r.json()["order"]
    assert o["order_number"] == "SA-10001" and o["status"] == "shipped"
    tent = next(i for i in o["items"] if i["slug"] == "ridgeline-2p-tent")
    assert tent == {"name": "Ridgeline 2-Person Tent", "slug": "ridgeline-2p-tent", "quantity": 1,
                    "unit_price": "$329.00", "line_total": "$329.00"}
    lamp = next(i for i in o["items"] if i["slug"] == "lumen-300-headlamp")
    assert lamp["quantity"] == 2 and lamp["line_total"] == "$78.00"
    assert o["carrier"] == "UPS" and o["tracking_number"]
    assert "updated_at" in o
    assert not (_keys(o) & FORBIDDEN_KEYS)


def test_new_checkout_order_shows_the_shipping_address(client):
    h = login(client, "store-a", JORDAN, PW_A)
    client.put("/api/stores/store-a/cart/items/lumen-300-headlamp", json={"quantity": 1}, headers=h)
    q = client.post("/api/stores/store-a/checkout/quote", json={}, headers=h).json()["cart"]
    addr = {"full_name": "Jordan Lee", "line1": "5 Pine St", "line2": "Unit 2", "city": "Portland", "region": "OR", "postal_code": "97205"}
    r = client.post("/api/stores/store-a/checkout", json={"shipping": addr, "expected_total_cents": q["total_cents"]},
                    headers={**h, "Idempotency-Key": "phase-e-detail-key-0001"})
    assert r.status_code == 201, r.text
    number = r.json()["order"]["order_number"]
    try:
        o = client.get(f"/api/stores/store-a/orders/{number}", headers=h).json()["order"]
        assert o["shipping_address"] == {"name": "Jordan Lee", "line1": "5 Pine St", "line2": "Unit 2", "city": "Portland",
                                         "region": "OR", "postal_code": "97205", "country": "US", "country_name": "United States",
                                         "phone": None}   # US phone is optional (country-aware checkout)
        assert o["awaiting_payment"] is True and o["subtotal"] and o["shipping"]
    finally:
        client.post(f"/api/stores/store-a/orders/{number}/cancel", headers=h)


def test_other_customers_order_is_indistinguishable_from_missing(client):
    h = login(client, "store-a", JORDAN, PW_A)
    other = client.get("/api/stores/store-a/orders/SA-10001", headers=h)     # Alex's order
    missing = client.get("/api/stores/store-a/orders/SA-99999", headers=h)
    assert other.status_code == missing.status_code == 404
    assert other.json() == missing.json()


def test_order_detail_requires_sign_in(client):
    assert client.get("/api/stores/store-a/orders/SA-10001").status_code == 401


def test_store_b_session_cannot_read_store_a_order(client):
    # Alex has an account in BOTH stores; a Store B token must not open a Store A order.
    hb = login(client, "store-b", ALEX, PW_B)
    assert client.get("/api/stores/store-a/orders/SA-10001", headers=hb).status_code == 403   # token bound to Store B
    # and a Store B customer asking Store B for a Store A order number gets nothing
    hm = login(client, "store-b", MARIA, PW_B)
    assert client.get("/api/stores/store-b/orders/SA-10001", headers=hm).status_code in (404, 422)


def test_agent_sees_detail_in_own_store_only(client):
    h = login(client, "store-a", AGENT_A, AGENT_PASSWORD)
    r = client.get("/api/stores/store-a/orders/SA-10004", headers=h)
    assert r.status_code == 200 and r.json()["order"]["order_number"] == "SA-10004"
    assert client.get("/api/stores/store-b/orders/BB-20001", headers=h).status_code == 403

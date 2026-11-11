"""Phase F: staff fulfilment — authorisation, validated transitions, tracking, history with actors, store isolation."""

from __future__ import annotations

import pytest

from app.seed import AGENT_PASSWORD

from .conftest import ADDRESS_A, ADDRESS_B, AGENT_A, AGENT_B, db_exec, idem, login, new_customer, set_stock

LAMP, HONEY = "lumen-300-headlamp", "wildflower-honey"
SHIP = {"carrier": "Blue Dart", "tracking_number": "bd123456789in", "tracking_url": "https://track.example.org/BD123456789IN"}


def _paid_order(client, store="store-a"):
    slug, addr, prefix = (LAMP, ADDRESS_A, "store-a") if store == "store-a" else (HONEY, ADDRESS_B, "store-b")
    set_stock(client.app.state.settings, store, slug, 60)
    headers, _ = new_customer(client, store)
    client.post(f"/api/stores/{store}/cart/items", json={"slug": slug, "quantity": 1}, headers=headers)
    total = client.post(f"/api/stores/{store}/checkout/quote", json={}, headers=headers).json()["cart"]["total_cents"]
    r = client.post(f"/api/stores/{store}/checkout", headers={**headers, **idem()}, json={"shipping": addr, "expected_total_cents": total})
    assert r.status_code == 201, r.text
    number = r.json()["order"]["order_number"]
    ref = client.post(f"/api/stores/{store}/orders/{number}/payments", headers=headers).json()["payment"]["reference"]
    client.post(f"/api/stores/{store}/payments/sandbox/{ref}/complete", headers=headers, json={"outcome": "success"})
    paid = client.post(f"/api/stores/{store}/orders/{number}/payments/verify", headers=headers).json()
    assert paid["order"]["status"] == "processing"
    return headers, number


@pytest.fixture
def agent_a(client):
    return login(client, "store-a", AGENT_A, AGENT_PASSWORD)


def _act(client, h, number, action, body, store="store-a", method="post"):
    return getattr(client, method)(f"/api/stores/{store}/staff/orders/{number}/{action}", headers=h, json=body)


# ---- authorisation ------------------------------------------------------------------------------------------------
STAFF_CALLS = [("get", "/staff/orders", None), ("get", "/staff/orders/SA-10003", None),
               ("post", "/staff/orders/SA-10003/ship", {"expected_status": "processing", **SHIP}),
               ("post", "/staff/orders/SA-10001/deliver", {"expected_status": "shipped"}),
               ("post", "/staff/orders/SA-10002/return", {"expected_status": "delivered", "note": "came back"}),
               ("put", "/staff/orders/SA-10001/tracking", SHIP)]


@pytest.mark.parametrize("method, path, body", STAFF_CALLS)
def test_staff_endpoints_need_sign_in(client, method, path, body):
    r = client.request(method.upper(), f"/api/stores/store-a{path}", json=body)
    assert r.status_code == 401


@pytest.mark.parametrize("method, path, body", STAFF_CALLS)
def test_customers_cannot_use_staff_endpoints(client, method, path, body):
    headers, _ = new_customer(client, "store-a")
    r = client.request(method.upper(), f"/api/stores/store-a{path}", headers=headers, json=body)
    assert r.status_code == 403
    assert client.get("/api/stores/store-a/staff/orders/SA-10003", headers=login(client, "store-a", AGENT_A, AGENT_PASSWORD)).json()["order"]["status"] == "processing"


@pytest.mark.parametrize("method, path, body", STAFF_CALLS)
def test_store_b_staff_cannot_touch_store_a(client, method, path, body):
    hb = login(client, "store-b", AGENT_B, AGENT_PASSWORD)
    assert client.request(method.upper(), f"/api/stores/store-a{path}", headers=hb, json=body).status_code == 403


def test_store_a_staff_see_only_store_a_orders(client, agent_a):
    r = client.get("/api/stores/store-a/staff/orders", headers=agent_a, params={"limit": 100})
    assert r.status_code == 200
    numbers = [o["order_number"] for o in r.json()["orders"]]
    assert numbers and all(n.startswith("SA-") for n in numbers)
    assert client.get("/api/stores/store-a/staff/orders/BB-20001", headers=agent_a).status_code == 404


def test_customer_endpoints_accept_no_fulfilment_fields(client):
    headers, _ = new_customer(client, "store-a")
    client.post("/api/stores/store-a/cart/items", json={"slug": LAMP, "quantity": 1}, headers=headers)
    r = client.post("/api/stores/store-a/checkout", headers={**headers, **idem()},
                    json={"shipping": ADDRESS_A, "expected_total_cents": 4595, "status": "shipped", "tracking_number": "X1234"})
    assert r.status_code == 422


# ---- the fulfilment path --------------------------------------------------------------------------------------------
def test_full_path_ship_out_for_delivery_deliver_return_with_history(client, agent_a):
    customer, number = _paid_order(client)
    r = _act(client, agent_a, number, "ship", {"expected_status": "processing", **SHIP, "estimated_delivery": "2026-12-01", "note": "packed by A"})
    assert r.status_code == 200, r.text
    o = r.json()["order"]
    assert o["status"] == "shipped" and o["carrier"] == "Blue Dart" and o["tracking_number"] == "BD123456789IN"
    assert o["tracking_url"] == SHIP["tracking_url"] and o["estimated_delivery"] == "2026-12-01" and o["shipped_at"]
    assert o["actions"] == ["out_for_delivery", "deliver", "return"]
    assert _act(client, agent_a, number, "out-for-delivery", {"expected_status": "shipped"}).json()["order"]["status"] == "out_for_delivery"
    d = _act(client, agent_a, number, "deliver", {"expected_status": "out_for_delivery"}).json()["order"]
    assert d["status"] == "delivered" and d["delivered_at"] and d["actions"] == ["return"]
    ret = _act(client, agent_a, number, "return", {"expected_status": "delivered", "note": "customer sent it back unopened"}).json()["order"]
    assert ret["status"] == "returned" and ret["actions"] == []

    history = ret["history"]
    assert [(h["from_status"], h["status"]) for h in history] == [
        (None, "pending_payment"), ("pending_payment", "processing"), ("processing", "shipped"),
        ("shipped", "out_for_delivery"), ("out_for_delivery", "delivered"), ("delivered", "returned")]
    assert [h["actor_role"] for h in history] == ["customer", "system", "agent", "agent", "agent", "agent"]
    assert history[2]["actor_name"] == "Summit Support Agent" and history[2]["note"] == "packed by A"
    assert history[2]["carrier"] == "Blue Dart" and history[2]["tracking_number"] == "BD123456789IN"
    assert history[5]["note"] == "customer sent it back unopened"

    # The customer sees tracking and the status timeline — but no staff notes and no staff identity.
    c = client.get(f"/api/stores/store-a/orders/{number}", headers=customer).json()["order"]
    assert c["status"] == "returned" and c["tracking_url"] == SHIP["tracking_url"]
    assert [h["status"] for h in c["history"]] == ["pending_payment", "processing", "shipped", "out_for_delivery", "delivered", "returned"]
    flat = str(c)
    assert "packed by A" not in flat and "unopened" not in flat and "Summit Support Agent" not in flat and "actor" not in flat


@pytest.mark.parametrize("action, body, from_status", [
    ("deliver", {}, "processing"), ("return", {"note": "nope"}, "processing"), ("out-for-delivery", {}, "processing")])
def test_invalid_transitions_are_refused(client, agent_a, action, body, from_status):
    _, number = _paid_order(client)
    r = _act(client, agent_a, number, action, {"expected_status": from_status, **body})
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"
    assert client.get(f"/api/stores/store-a/staff/orders/{number}", headers=agent_a).json()["order"]["status"] == "processing"


def test_unpaid_and_cancelled_orders_cannot_be_shipped(client, agent_a):
    headers, _ = new_customer(client, "store-a")
    set_stock(client.app.state.settings, "store-a", LAMP, 60)
    client.post("/api/stores/store-a/cart/items", json={"slug": LAMP, "quantity": 1}, headers=headers)
    number = client.post("/api/stores/store-a/checkout", headers={**headers, **idem()},
                         json={"shipping": ADDRESS_A, "expected_total_cents": 4595}).json()["order"]["order_number"]
    assert _act(client, agent_a, number, "ship", {"expected_status": "pending_payment", **SHIP}).status_code == 409
    client.post(f"/api/stores/store-a/orders/{number}/cancel", headers=headers)
    assert _act(client, agent_a, number, "ship", {"expected_status": "cancelled", **SHIP}).status_code == 409


def test_stale_screen_cannot_act_twice(client, agent_a):
    _, number = _paid_order(client)
    assert _act(client, agent_a, number, "ship", {"expected_status": "processing", **SHIP}).status_code == 200
    again = _act(client, agent_a, number, "ship", {"expected_status": "processing", **SHIP})
    assert again.status_code == 409 and again.json()["error"]["code"] == "stale_status"
    o = client.get(f"/api/stores/store-a/staff/orders/{number}", headers=agent_a).json()["order"]
    assert sum(1 for h in o["history"] if h["status"] == "shipped") == 1


@pytest.mark.parametrize("override", [
    {"tracking_url": "http://track.example.org/1"}, {"tracking_url": "javascript:alert(1)"}, {"tracking_url": "https://x y"},
    {"carrier": "<script>"}, {"carrier": ""}, {"tracking_number": "ab"}, {"tracking_number": "12 34 56"},
    {"status": "delivered"}, {"note": "x" * 501}])
def test_ship_input_validation(client, agent_a, override):
    _, number = _paid_order(client)
    r = _act(client, agent_a, number, "ship", {"expected_status": "processing", **SHIP, **override})
    assert r.status_code == 422, r.text
    assert client.get(f"/api/stores/store-a/staff/orders/{number}", headers=agent_a).json()["order"]["status"] == "processing"


def test_return_requires_a_note(client, agent_a):
    _, number = _paid_order(client)
    _act(client, agent_a, number, "ship", {"expected_status": "processing", **SHIP})
    assert _act(client, agent_a, number, "return", {"expected_status": "shipped"}).status_code == 422
    assert _act(client, agent_a, number, "return", {"expected_status": "shipped", "note": "refused at door"}).status_code == 200


def test_tracking_can_be_corrected_only_while_in_transit(client, agent_a):
    _, number = _paid_order(client)
    assert _act(client, agent_a, number, "tracking", SHIP, method="put").status_code == 409   # still processing
    _act(client, agent_a, number, "ship", {"expected_status": "processing", **SHIP})
    fixed = {"carrier": "Delhivery", "tracking_number": "DLV0001", "tracking_url": None, "note": "label reprinted"}
    o = _act(client, agent_a, number, "tracking", fixed, method="put").json()["order"]
    assert o["carrier"] == "Delhivery" and o["tracking_number"] == "DLV0001" and o["tracking_url"] is None and o["status"] == "shipped"
    assert o["history"][-1]["note"] == "label reprinted" and o["history"][-1]["from_status"] == o["history"][-1]["status"] == "shipped"


def test_customer_cancellation_and_payment_are_recorded(client, agent_a):
    headers, _ = new_customer(client, "store-a")
    set_stock(client.app.state.settings, "store-a", LAMP, 60)
    client.post("/api/stores/store-a/cart/items", json={"slug": LAMP, "quantity": 1}, headers=headers)
    number = client.post("/api/stores/store-a/checkout", headers={**headers, **idem()},
                         json={"shipping": ADDRESS_A, "expected_total_cents": 4595}).json()["order"]["order_number"]
    client.post(f"/api/stores/store-a/orders/{number}/cancel", headers=headers)
    h = client.get(f"/api/stores/store-a/staff/orders/{number}", headers=agent_a).json()["order"]["history"]
    assert [(x["from_status"], x["status"], x["actor_role"], x["actor_name"]) for x in h] == [
        (None, "pending_payment", "customer", "Test Shopper"), ("pending_payment", "cancelled", "customer", "Test Shopper")]


def test_list_filters_and_paginates(client, agent_a):
    _, number = _paid_order(client)
    r = client.get("/api/stores/store-a/staff/orders", headers=agent_a, params={"status": ["processing"], "limit": 100}).json()
    assert number in [o["order_number"] for o in r["orders"]]
    assert all(o["status"] == "processing" and o["actions"] == ["ship"] for o in r["orders"])
    one = client.get("/api/stores/store-a/staff/orders", headers=agent_a, params={"q": number}).json()
    assert [o["order_number"] for o in one["orders"]] == [number] and one["total"] == 1
    page = client.get("/api/stores/store-a/staff/orders", headers=agent_a, params={"limit": 2, "offset": 1}).json()
    assert len(page["orders"]) == 2 and page["total"] >= 3
    assert client.get("/api/stores/store-a/staff/orders", headers=agent_a, params={"status": ["bogus"]}).status_code == 422
    assert client.get("/api/stores/store-a/staff/orders", headers=agent_a, params={"q": "%_%"}).status_code == 200   # escaped LIKE


def test_staff_detail_has_no_internal_ids(client, agent_a):
    o = client.get("/api/stores/store-a/staff/orders/SA-10001", headers=agent_a).json()["order"]
    assert o["customer_name"] == "Alex Rivera"
    flat = str(o)
    assert "'id'" not in flat and "customer_id" not in flat and "password" not in flat and "email" not in flat


def test_history_table_rejects_inconsistent_actor(settings):
    import psycopg
    with pytest.raises(psycopg.errors.CheckViolation):
        db_exec(settings, "store-a", "INSERT INTO order_status_history (order_id, to_status, actor_role, actor_customer_id) "
                                     "SELECT id, 'shipped', 'system', 1 FROM orders LIMIT 1")

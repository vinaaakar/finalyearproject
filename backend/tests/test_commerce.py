"""Cart and checkout: server-side pricing, stock validation, idempotency, store separation."""

import threading
import uuid

from tests.conftest import ADDRESS_A, ADDRESS_B, AGENT_A, PW_AGENT, db_exec, idem, login, new_customer, set_stock

LAMP = "lumen-300-headlamp"        # Store A, $39.00
STOVE = "pocketflame-stove"        # Store A, $49.00
TENT = "ridgeline-2p-tent"         # Store A, $329.00
HONEY = "wildflower-honey"         # Store B, $11.00


def add(client, store, slug, qty=1, headers=None):
    return client.post(f"/api/stores/{store}/cart/items", json={"slug": slug, "quantity": qty}, headers=headers or {})


def checkout(client, store, headers, address, total, key=None, method="standard"):
    return client.post(f"/api/stores/{store}/checkout", headers={**headers, **(key or idem())},
                       json={"shipping": address, "shipping_method": method, "expected_total_cents": total})


# ---- cart ------------------------------------------------------------------------------------
def test_guest_cart_gets_token_and_server_totals(client):
    set_stock(client.app.state.settings, "store-a", LAMP, 75)
    r = add(client, "store-a", LAMP, 2)
    assert r.status_code == 200
    token = r.json()["cart_token"]
    cart = client.get("/api/stores/store-a/cart", headers={"X-Cart-Token": token}).json()["cart"]
    assert cart["subtotal_cents"] == 7800 and cart["item_count"] == 2
    assert cart["shipping_cents"] == 0 and cart["total_cents"] == 7800  # $78 is over Store A's $75 free-shipping threshold

def test_shipping_rules_follow_store_policy(client):
    s = client.app.state.settings
    set_stock(s, "store-a", LAMP, 75)
    set_stock(s, "store-b", HONEY, 64)
    tok_a = add(client, "store-a", LAMP, 1).json()["cart_token"]
    a = client.get("/api/stores/store-a/cart", headers={"X-Cart-Token": tok_a}).json()["cart"]
    assert (a["subtotal_cents"], a["shipping_cents"]) == (3900, 695)             # under $75 → $6.95
    a = client.put(f"/api/stores/store-a/cart/items/{LAMP}", json={"quantity": 2}, headers={"X-Cart-Token": tok_a}).json()["cart"]
    assert (a["subtotal_cents"], a["shipping_cents"]) == (7800, 0)               # $75+ → free
    assert [o["method"] for o in a["shipping_options"]] == ["standard", "expedited"]
    tok_b = add(client, "store-b", HONEY, 1).json()["cart_token"]
    b = client.get("/api/stores/store-b/cart", headers={"X-Cart-Token": tok_b}).json()["cart"]
    assert (b["subtotal_cents"], b["shipping_cents"]) == (1100, 499)             # Store B: $4.99
    assert [o["method"] for o in b["shipping_options"]] == ["standard"]          # no expedited in Store B


def test_cart_quantity_change_and_remove(client):
    set_stock(client.app.state.settings, "store-a", STOVE, 60)
    tok = {"X-Cart-Token": add(client, "store-a", STOVE).json()["cart_token"]}
    add(client, "store-a", STOVE, 2, tok)
    assert client.get("/api/stores/store-a/cart", headers=tok).json()["cart"]["items"][0]["quantity"] == 3
    assert client.put(f"/api/stores/store-a/cart/items/{STOVE}", json={"quantity": 1}, headers=tok).json()["cart"]["item_count"] == 1
    assert client.delete(f"/api/stores/store-a/cart/items/{STOVE}", headers=tok).json()["cart"]["items"] == []


def test_cart_rejects_out_of_stock_and_over_stock(client):
    s = client.app.state.settings
    assert add(client, "store-a", "basecamp-4p-tent").status_code == 409          # seeded with 0 stock
    set_stock(s, "store-a", "stormshell-rain-jacket", 3)
    r = add(client, "store-a", "stormshell-rain-jacket", 4)
    assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_stock"
    assert add(client, "store-a", "no-such-product").status_code == 404
    assert add(client, "store-a", LAMP, 11).status_code == 422                     # per-line limit


def test_client_cannot_set_prices(client):
    r = client.post("/api/stores/store-a/cart/items", json={"slug": LAMP, "quantity": 1, "price_cents": 1})
    assert r.status_code == 422


def test_cart_shows_problem_when_stock_drops(client):
    s = client.app.state.settings
    set_stock(s, "store-a", STOVE, 60)
    tok = {"X-Cart-Token": add(client, "store-a", STOVE, 5).json()["cart_token"]}
    set_stock(s, "store-a", STOVE, 2)
    cart = client.get("/api/stores/store-a/cart", headers=tok).json()["cart"]
    assert cart["can_checkout"] is False and "Only 2" in cart["problems"][0]
    set_stock(s, "store-a", STOVE, 60)


def test_carts_are_separate_per_store(client):
    set_stock(client.app.state.settings, "store-a", LAMP, 75)
    tok = {"X-Cart-Token": add(client, "store-a", LAMP).json()["cart_token"]}
    # The Store A cart token means nothing to Store B (separate database).
    assert client.get("/api/stores/store-b/cart", headers=tok).json()["cart"]["items"] == []
    # And Store A products cannot be put into a Store B cart.
    assert add(client, "store-b", LAMP).status_code == 404


def test_signed_in_cart_and_guest_merge(client):
    s = client.app.state.settings
    set_stock(s, "store-a", LAMP, 75)
    set_stock(s, "store-a", STOVE, 60)
    headers, _ = new_customer(client, "store-a")
    add(client, "store-a", STOVE, 1, headers)
    guest = {"X-Cart-Token": add(client, "store-a", LAMP, 2).json()["cart_token"]}
    merged = client.post("/api/stores/store-a/cart/merge", headers={**headers, **guest}).json()["cart"]
    assert sorted((i["slug"], i["quantity"]) for i in merged["items"]) == [(LAMP, 2), (STOVE, 1)]
    # The guest cart is gone after the merge.
    assert client.get("/api/stores/store-a/cart", headers=guest).json()["cart"]["items"] == []


def test_store_a_token_cannot_use_store_b_cart(client):
    headers, _ = new_customer(client, "store-a")
    assert client.get("/api/stores/store-b/cart", headers=headers).status_code == 403
    assert add(client, "store-b", HONEY, 1, headers).status_code == 403


def test_agents_cannot_shop(client):
    headers = login(client, "store-a", AGENT_A, PW_AGENT)
    assert add(client, "store-a", LAMP, 1, headers).status_code == 403


# ---- checkout ---------------------------------------------------------------------------------
def _ready_customer(client, store="store-a", slug=LAMP, qty=1, stock=75):
    set_stock(client.app.state.settings, store, slug, stock)
    headers, email = new_customer(client, store)
    assert add(client, store, slug, qty, headers).status_code == 200
    return headers


def test_checkout_requires_sign_in(client):
    r = client.post("/api/stores/store-a/checkout", headers=idem(), json={"shipping": ADDRESS_A, "expected_total_cents": 1})
    assert r.status_code == 401


def test_checkout_creates_order_transactionally(client):
    s = client.app.state.settings
    headers = _ready_customer(client, qty=2, stock=75)
    quote = client.post("/api/stores/store-a/checkout/quote", json={"shipping_method": "standard"}, headers=headers).json()["cart"]
    r = checkout(client, "store-a", headers, ADDRESS_A, quote["total_cents"])
    assert r.status_code == 201, r.text
    order = r.json()["order"]
    assert order["order_number"].startswith("SA-5") and order["status"] == "pending_payment" and order["awaiting_payment"]
    assert order["total"] == "$78.00" and order["items"] == [{"name": "Lumen 300 Headlamp", "slug": LAMP, "quantity": 2}]
    assert db_exec(s, "store-a", "SELECT stock_qty FROM products WHERE slug = %s", [LAMP])[0][0] == 73
    # Cart is emptied, and the order is visible in the customer's order list.
    assert client.get("/api/stores/store-a/cart", headers=headers).json()["cart"]["items"] == []
    assert [o["order_number"] for o in client.get("/api/stores/store-a/orders", headers=headers).json()["orders"]] == [order["order_number"]]


def test_checkout_is_idempotent(client):
    s = client.app.state.settings
    headers = _ready_customer(client, stock=75)
    key = idem()
    first = checkout(client, "store-a", headers, ADDRESS_A, 3900 + 695, key)
    again = checkout(client, "store-a", headers, ADDRESS_A, 3900 + 695, key)
    assert first.status_code == 201 and again.status_code == 200
    assert first.json()["order"]["order_number"] == again.json()["order"]["order_number"]
    assert again.json()["created"] is False
    assert db_exec(s, "store-a", "SELECT stock_qty FROM products WHERE slug = %s", [LAMP])[0][0] == 74
    # A *different* key after the cart was converted does not create a second order either.
    assert checkout(client, "store-a", headers, ADDRESS_A, 3900 + 695).json()["error"]["code"] == "cart_empty"


def test_concurrent_duplicate_submissions_create_one_order(client):
    s = client.app.state.settings
    headers = _ready_customer(client, stock=75)
    key = idem()
    results = []

    def submit():
        results.append(checkout(client, "store-a", headers, ADDRESS_A, 3900 + 695, key))

    threads = [threading.Thread(target=submit) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    numbers = {r.json()["order"]["order_number"] for r in results}
    assert len(numbers) == 1 and sorted(r.status_code for r in results) == [200, 200, 200, 201]
    assert db_exec(s, "store-a", "SELECT stock_qty FROM products WHERE slug = %s", [LAMP])[0][0] == 74


def test_checkout_rechecks_stock(client):
    s = client.app.state.settings
    headers = _ready_customer(client, slug=STOVE, qty=3, stock=60)
    set_stock(s, "store-a", STOVE, 2)
    r = checkout(client, "store-a", headers, ADDRESS_A, 3 * 4900 + 695)
    assert r.status_code == 409 and r.json()["error"]["code"] == "stock_changed"
    assert db_exec(s, "store-a", "SELECT count(*) FROM orders WHERE idempotency_key IS NOT NULL AND status = 'pending_payment' "
                   "AND id IN (SELECT order_id FROM order_items oi JOIN products p ON p.id = oi.product_id WHERE p.slug = %s AND oi.quantity = 3)",
                   [STOVE])[0][0] == 0
    set_stock(s, "store-a", STOVE, 60)


def test_checkout_rechecks_price(client):
    s = client.app.state.settings
    headers = _ready_customer(client, stock=75)
    db_exec(s, "store-a", "UPDATE products SET price_cents = 4500 WHERE slug = %s", [LAMP])
    try:
        r = checkout(client, "store-a", headers, ADDRESS_A, 3900 + 695)   # the total the customer reviewed earlier
        assert r.status_code == 409 and r.json()["error"]["code"] == "total_changed"
        ok = checkout(client, "store-a", headers, ADDRESS_A, 4500 + 695)
        assert ok.status_code == 201 and ok.json()["order"]["total"] == "$51.95"
    finally:
        db_exec(s, "store-a", "UPDATE products SET price_cents = 3900 WHERE slug = %s", [LAMP])


def test_checkout_validates_address_server_side(client):
    headers = _ready_customer(client, stock=75)
    bad = [
        {**ADDRESS_A, "postal_code": "ABCDE"},
        {**ADDRESS_A, "region": "ZZ"},
        {**ADDRESS_A, "line1": "   "},
        {**ADDRESS_A, "country": "CA"},
    ]
    for addr in bad:
        assert checkout(client, "store-a", headers, addr, 4595).status_code == 422
    # Store A ships to the contiguous US only.
    r = checkout(client, "store-a", headers, {**ADDRESS_A, "region": "HI", "postal_code": "96813"}, 4595)
    assert r.status_code == 422 and r.json()["error"]["code"] == "region_not_served"


def test_checkout_never_accepts_card_details(client):
    headers = _ready_customer(client, stock=75)
    r = client.post("/api/stores/store-a/checkout", headers={**headers, **idem()},
                    json={"shipping": ADDRESS_A, "expected_total_cents": 4595, "card_number": "4242424242424242", "cvc": "123"})
    assert r.status_code == 422 and "4242" not in r.text


def test_checkout_requires_idempotency_key(client):
    headers = _ready_customer(client, stock=75)
    r = client.post("/api/stores/store-a/checkout", headers=headers, json={"shipping": ADDRESS_A, "expected_total_cents": 4595})
    assert r.status_code == 422


def test_expedited_only_where_offered(client):
    headers = _ready_customer(client, store="store-b", slug=HONEY, stock=64)
    r = checkout(client, "store-b", headers, ADDRESS_B, 1100 + 1495, method="expedited")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_shipping_method"
    a_headers = _ready_customer(client, stock=75)
    assert checkout(client, "store-a", a_headers, ADDRESS_A, 3900 + 1495, method="expedited").status_code == 201


def test_cancel_unpaid_order_restocks(client):
    s = client.app.state.settings
    headers = _ready_customer(client, qty=2, stock=75)
    number = checkout(client, "store-a", headers, ADDRESS_A, 7800).json()["order"]["order_number"]
    assert db_exec(s, "store-a", "SELECT stock_qty FROM products WHERE slug = %s", [LAMP])[0][0] == 73
    r = client.post(f"/api/stores/store-a/orders/{number}/cancel", headers=headers)
    assert r.status_code == 200 and r.json()["order"]["status"] == "cancelled"
    assert db_exec(s, "store-a", "SELECT stock_qty FROM products WHERE slug = %s", [LAMP])[0][0] == 75
    assert client.post(f"/api/stores/store-a/orders/{number}/cancel", headers=headers).status_code == 409


def test_other_customer_cannot_touch_order(client):
    headers = _ready_customer(client, stock=75)
    number = checkout(client, "store-a", headers, ADDRESS_A, 4595).json()["order"]["order_number"]
    other, _ = new_customer(client, "store-a")
    assert client.post(f"/api/stores/store-a/orders/{number}/cancel", headers=other).status_code == 404
    assert client.post(f"/api/stores/store-a/orders/{number}/payments", headers=other).status_code == 404
    assert client.get(f"/api/stores/store-a/orders/{number}", headers=other).status_code == 404


def test_new_order_reachable_by_phone_verification(client):
    headers = _ready_customer(client, stock=75)
    number = checkout(client, "store-a", headers, ADDRESS_A, 4595).json()["order"]["order_number"]
    cid = client.post("/api/phone/simulator/store-a/calls").json()["call_id"]
    client.post(f"/api/phone/simulator/calls/{cid}/turns", json={"speech": f"where is my order {number}"})
    r = client.post(f"/api/phone/simulator/calls/{cid}/turns", json={"digits": "80302"}).json()
    assert number in r["say"] and "awaiting payment" in r["say"]


def test_resubmit_with_same_key_after_adding_items_returns_original(client):
    s = client.app.state.settings
    set_stock(s, "store-a", STOVE, 60)
    headers = _ready_customer(client, stock=75)
    key = idem()
    first = checkout(client, "store-a", headers, ADDRESS_A, 4595, key).json()["order"]
    add(client, "store-a", STOVE, 1, headers)
    again = checkout(client, "store-a", headers, ADDRESS_A, 4900 + 695, key)
    assert again.status_code == 200 and again.json()["order"]["order_number"] == first["order_number"]
    # The new cart is untouched and its stock was not taken.
    assert client.get("/api/stores/store-a/cart", headers=headers).json()["cart"]["items"][0]["slug"] == STOVE
    assert db_exec(s, "store-a", "SELECT stock_qty FROM products WHERE slug = %s", [STOVE])[0][0] == 60

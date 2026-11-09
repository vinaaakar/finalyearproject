"""API contracts the storefront purchase journey relies on: product details, quantity limits, stock checks,
"Buy now" (add to cart, then the normal checkout) and account sign-in. Runs against the *_test databases."""

from tests.conftest import ADDRESS_A, ADDRESS_B, STRONG_PW, idem, login, new_customer, set_stock

LAMP = "lumen-300-headlamp"        # Store A, $39.00
JACKET = "stormshell-rain-jacket"  # Store A
OUT_A = "basecamp-4p-tent"         # Store A, seeded with 0 stock
HONEY = "wildflower-honey"         # Store B, $11.00


def add(client, store, slug, qty=1, headers=None):
    return client.post(f"/api/stores/{store}/cart/items", json={"slug": slug, "quantity": qty}, headers=headers or {})


def cart(client, store, headers):
    return client.get(f"/api/stores/{store}/cart", headers=headers).json()["cart"]


# ---- product details --------------------------------------------------------------------------
def test_every_product_detail_has_what_the_product_page_shows(client):
    for store in ("store-a", "store-b"):
        listed = client.get(f"/api/stores/{store}/products").json()["products"]
        assert len(listed) == 10
        for item in listed:
            p = client.get(f"/api/stores/{store}/products/{item['slug']}").json()["product"]
            assert p["name"] and p["description"] and p["category"]
            assert p["price"].startswith("$") and p["price_cents"] > 0
            assert isinstance(p["stock_qty"], int) and p["in_stock"] is (p["stock_qty"] > 0)


def test_product_detail_is_store_scoped(client):
    assert client.get(f"/api/stores/store-b/products/{LAMP}").status_code == 404
    assert client.get(f"/api/stores/store-a/products/{HONEY}").status_code == 404


# ---- quantity limits and stock ------------------------------------------------------------------
def test_repeated_adds_cannot_pass_the_per_item_limit(client):
    set_stock(client.app.state.settings, "store-a", LAMP, 75)
    tok = {"X-Cart-Token": add(client, "store-a", LAMP, 6).json()["cart_token"]}
    r = add(client, "store-a", LAMP, 5, tok)
    assert r.status_code == 409 and r.json()["error"]["code"] == "quantity_limit"
    assert cart(client, "store-a", tok)["items"][0]["quantity"] == 6          # unchanged by the refused add
    line = cart(client, "store-a", tok)["items"][0]
    assert line["max_quantity"] == 10                                        # what the cart's picker offers


def test_adds_cannot_pass_available_stock_in_total(client):
    s = client.app.state.settings
    set_stock(s, "store-a", JACKET, 3)
    try:
        tok = {"X-Cart-Token": add(client, "store-a", JACKET, 2).json()["cart_token"]}
        r = add(client, "store-a", JACKET, 2, tok)
        assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_stock"
        assert "Only 3" in r.json()["error"]["message"]
        line = cart(client, "store-a", tok)["items"][0]
        assert line["quantity"] == 2 and line["max_quantity"] == 3
        # Setting a quantity above stock is refused too (the cart page's picker).
        assert client.put(f"/api/stores/store-a/cart/items/{JACKET}", json={"quantity": 4}, headers=tok).status_code == 409
    finally:
        set_stock(s, "store-a", JACKET, 3)


def test_out_of_stock_product_cannot_be_added_or_checked_out(client):
    s = client.app.state.settings
    r = add(client, "store-a", OUT_A)
    assert r.status_code == 409 and r.json()["error"]["code"] == "out_of_stock" and "cart_token" not in r.json()
    # An item that sells out after it was added blocks checkout until it is removed.
    headers, _ = new_customer(client, "store-a")
    set_stock(s, "store-a", LAMP, 5)
    try:
        assert add(client, "store-a", LAMP, 1, headers).status_code == 200
        set_stock(s, "store-a", LAMP, 0)
        c = cart(client, "store-a", headers)
        assert c["can_checkout"] is False and "out of stock" in c["problems"][0]
        r = client.post("/api/stores/store-a/checkout", headers={**headers, **idem()},
                        json={"shipping": ADDRESS_A, "shipping_method": "standard", "expected_total_cents": c["total_cents"]})
        assert r.status_code == 409
    finally:
        set_stock(s, "store-a", LAMP, 75)


def test_invalid_quantities_are_rejected(client):
    for qty in (0, -1, 11, "two"):
        assert add(client, "store-b", HONEY, qty).status_code == 422


# ---- "Buy now" = add to the cart, then the existing checkout ------------------------------------
def test_buy_now_goes_through_the_normal_cart_and_checkout(client):
    s = client.app.state.settings
    set_stock(s, "store-b", HONEY, 64)
    # A guest presses Buy now: the item goes into the guest cart ...
    guest = {"X-Cart-Token": add(client, "store-b", HONEY, 2).json()["cart_token"]}
    # ... then signs up on the way to checkout; the guest cart is merged into the new account.
    email = "buynow-shopper@example.com"
    r = client.post("/api/stores/store-b/auth/register", json={"email": email, "full_name": "Buy Now", "password": STRONG_PW})
    assert r.status_code == 201
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    merged = client.post("/api/stores/store-b/cart/merge", headers={**headers, **guest}).json()["cart"]
    assert [(i["slug"], i["quantity"]) for i in merged["items"]] == [(HONEY, 2)]
    quote = client.post("/api/stores/store-b/checkout/quote", json={"shipping_method": "standard"}, headers=headers).json()["cart"]
    r = client.post("/api/stores/store-b/checkout", headers={**headers, **idem()},
                    json={"shipping": ADDRESS_B, "shipping_method": "standard", "expected_total_cents": quote["total_cents"]})
    assert r.status_code == 201, r.text
    order = r.json()["order"]
    assert order["status"] == "pending_payment" and order["items"] == [{"name": "Wildflower Honey", "slug": HONEY, "quantity": 2}]
    assert cart(client, "store-b", headers)["items"] == []
    # Not paid until the sandbox payment is verified by the server.
    assert client.get(f"/api/stores/store-b/orders/{order['order_number']}/payment", headers=headers).json()["payment"] is None


# ---- accounts, as used by the sign-in and registration pages ------------------------------------
def test_registration_signs_in_and_the_account_works(client):
    email = "new-trail-shopper@example.com"
    r = client.post("/api/stores/store-a/auth/register", json={"email": email, "full_name": "Trail Shopper", "password": STRONG_PW})
    assert r.status_code == 201 and r.json()["customer"]["email"] == email
    me = client.get("/api/stores/store-a/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == email
    assert login(client, "store-a", email, STRONG_PW)
    # The account belongs to Store A only.
    assert client.post("/api/stores/store-b/auth/login", json={"email": email, "password": STRONG_PW}).status_code == 401


def test_registration_errors_name_the_field(client):
    r = client.post("/api/stores/store-a/auth/register", json={"email": "short-pw@example.com", "full_name": "Short", "password": "abc"})
    assert r.status_code == 422
    # Password strength is a whole-request check: reported as "body" with a message naming the password,
    # which the registration form shows under the password field.
    assert any(d["field"] == "body" and d["issue"].startswith("password") for d in r.json()["error"]["details"])
    assert "abc" not in r.text                                               # the value is never echoed
    r = client.post("/api/stores/store-a/auth/register", json={"email": "not-an-email", "full_name": "X", "password": STRONG_PW})
    assert r.status_code == 422 and any(d["field"] == "email" for d in r.json()["error"]["details"])

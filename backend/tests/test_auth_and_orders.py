from tests.conftest import AGENT_A, ALEX, JORDAN, PW_A, PW_AGENT, login


def test_login_wrong_password_and_unknown_email_look_identical(client):
    r1 = client.post("/api/stores/store-a/auth/login", json={"email": ALEX, "password": "wrong"})
    r2 = client.post("/api/stores/store-a/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


def test_orders_require_login(client):
    assert client.get("/api/stores/store-a/orders").status_code == 401
    assert client.get("/api/stores/store-a/orders/SA-10001").status_code == 401


def test_customer_sees_own_order(client):
    r = client.get("/api/stores/store-a/orders/SA-10001", headers=login(client, "store-a", ALEX, PW_A))
    assert r.status_code == 200
    assert r.json()["order"]["status"] == "shipped"


def test_customer_cannot_see_another_customers_order(client):
    # SA-10003 belongs to Jordan.
    r = client.get("/api/stores/store-a/orders/SA-10003", headers=login(client, "store-a", ALEX, PW_A))
    assert r.status_code == 404


def test_admin_orders_require_agent_role(client):
    assert client.get("/api/stores/store-a/admin/orders", headers=login(client, "store-a", JORDAN, PW_A)).status_code == 403
    r = client.get("/api/stores/store-a/admin/orders", headers=login(client, "store-a", AGENT_A, PW_AGENT))
    assert r.status_code == 200 and len(r.json()["orders"]) == 5


def test_agent_can_view_any_order_in_own_store(client):
    r = client.get("/api/stores/store-a/orders/SA-10003", headers=login(client, "store-a", AGENT_A, PW_AGENT))
    assert r.status_code == 200


def test_malformed_auth_headers(client):
    assert client.get("/api/stores/store-a/orders", headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.get("/api/stores/store-a/orders", headers={"Authorization": "Bearer not.valid"}).status_code == 401


def test_invalid_order_number_format_rejected(client):
    headers = login(client, "store-a", ALEX, PW_A)
    assert client.get("/api/stores/store-a/orders/1;DROP TABLE orders", headers=headers).status_code in (404, 422)
    assert client.get("/api/stores/store-a/orders/SA-1", headers=headers).status_code == 422


def test_validation_error_does_not_echo_input(client):
    r = client.post("/api/stores/store-a/auth/login", json={"email": "not-an-email", "password": "SuperSecret123"})
    assert r.status_code == 422
    assert "SuperSecret123" not in r.text and "not-an-email" not in r.text
    assert r.json()["error"]["code"] == "validation_error"

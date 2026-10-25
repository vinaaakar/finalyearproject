"""Proof that Store A and Store B data never cross — at the API, assistant, phone and database-role levels."""

import psycopg
import pytest

from tests.conftest import AGENT_A, ALEX, JORDAN, MARIA, PW_A, PW_AGENT, PW_B, login


def slugs(client, store):
    return {p["slug"] for p in client.get(f"/api/stores/{store}/products").json()["products"]}


def test_catalogs_are_disjoint(client):
    a, b = slugs(client, "store-a"), slugs(client, "store-b")
    assert a and b and a.isdisjoint(b)


def test_store_b_product_not_reachable_via_store_a(client):
    assert client.get("/api/stores/store-b/products/gooseneck-kettle").status_code == 200
    assert client.get("/api/stores/store-a/products/gooseneck-kettle").status_code == 404


def test_search_only_returns_own_store_products(client):
    r = client.get("/api/stores/store-a/products", params={"q": "coffee"})
    assert r.status_code == 200
    assert all("coffee" not in p["category"].lower() for p in r.json()["products"])


def test_unknown_store_rejected(client):
    assert client.get("/api/stores/store-c/products").status_code == 422
    assert client.get("/api/stores/STORE-A/products").status_code == 422


def test_customer_accounts_are_per_store(client):
    # Maria only has a Store B account.
    r = client.post("/api/stores/store-a/auth/login", json={"email": MARIA, "password": PW_B})
    assert r.status_code == 401
    # Alex has an account in each store with that store's password only.
    assert client.post("/api/stores/store-a/auth/login", json={"email": ALEX, "password": PW_B}).status_code == 401


def test_same_email_sees_only_that_stores_orders(client):
    a_orders = client.get("/api/stores/store-a/orders", headers=login(client, "store-a", ALEX, PW_A)).json()["orders"]
    b_orders = client.get("/api/stores/store-b/orders", headers=login(client, "store-b", ALEX, PW_B)).json()["orders"]
    assert a_orders and all(o["order_number"].startswith("SA-") for o in a_orders)
    assert b_orders and all(o["order_number"].startswith("BB-") for o in b_orders)


@pytest.mark.parametrize("path", ["/orders", "/me", "/orders/BB-20002"])
def test_store_a_token_rejected_by_store_b(client, path):
    headers = login(client, "store-a", ALEX, PW_A)
    r = client.get(f"/api/stores/store-b{path}", headers=headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


def test_store_a_token_rejected_by_store_b_chat(client):
    headers = login(client, "store-a", ALEX, PW_A)
    r = client.post("/api/stores/store-b/chat", json={"message": "where is my order BB-20002"}, headers=headers)
    assert r.status_code == 403


def test_store_b_order_not_visible_from_store_a(client):
    headers = login(client, "store-a", ALEX, PW_A)
    # BB-20002 belongs to Alex's *Store B* account; Store A must not reveal it.
    assert client.get("/api/stores/store-a/orders/BB-20002", headers=headers).status_code == 404


def test_store_a_assistant_does_not_reveal_store_b_order(client):
    headers = login(client, "store-a", ALEX, PW_A)
    r = client.post("/api/stores/store-a/chat", json={"message": "What's the status of order BB-20002?"}, headers=headers)
    body = r.json()
    assert r.status_code == 200
    assert body["orders"] == []
    assert "processing" not in body["reply"].lower()
    assert "Bloom" not in body["reply"]


def test_store_a_agent_cannot_access_store_b(client):
    headers = login(client, "store-a", AGENT_A, PW_AGENT)
    assert client.get("/api/stores/store-b/admin/orders", headers=headers).status_code == 403
    assert client.get("/api/stores/store-a/orders/BB-20001", headers=headers).status_code == 404
    listed = client.get("/api/stores/store-a/admin/orders", headers=headers).json()["orders"]
    assert listed and all(o["order_number"].startswith("SA-") for o in listed)


def test_tampered_token_store_claim_rejected(client):
    import base64, json

    token = login(client, "store-a", JORDAN, PW_A)["Authorization"].split()[1]
    body, sig = token.split(".")
    payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    payload["store"] = "store-b"
    forged = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode() + "." + sig
    r = client.get("/api/stores/store-b/orders", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_phone_flow_cannot_verify_other_store_order(client):
    call = client.post("/api/phone/simulator/store-a/calls").json()
    cid = call["call_id"]
    client.post(f"/api/phone/simulator/calls/{cid}/turns", json={"speech": "where is my order BB-20001"})
    r = client.post(f"/api/phone/simulator/calls/{cid}/turns", json={"digits": "60614"})  # correct ZIP for the Store B order
    assert "don't match" in r.json()["say"]


def test_database_roles_cannot_cross_connect(settings):
    a_url = settings.store_database_urls["store-a"]
    b_url = settings.store_database_urls["store-b"]
    # Store A's role pointed at Store B's database must be refused by Postgres itself.
    a_role_on_b = b_url.replace(b_url.split("//")[1].split("@")[0], a_url.split("//")[1].split("@")[0])
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(a_role_on_b, connect_timeout=5).close()

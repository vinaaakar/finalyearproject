"""Phase J: cookie sessions (AUTH_COOKIES=true) — HttpOnly/SameSite cookies scoped per store, CSRF double-submit on every
state-changing request, revocation (sign-out, sign-out everywhere); bearer mode keeps working."""

from __future__ import annotations

import pytest

from app.seed import DEMO_PASSWORDS
from app.stores import StoreId

from .conftest import ALEX, JORDAN, login, make_client

PW_A, PW_B = DEMO_PASSWORDS[StoreId.STORE_A], DEMO_PASSWORDS[StoreId.STORE_B]


@pytest.fixture
def cookie_client(settings):
    with make_client(settings, auth_cookies=True) as c:
        yield c


def cookie_login(c, store="store-a", email=JORDAN, pw=PW_A):
    r = c.post(f"/api/stores/{store}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r


def test_cookie_login_keeps_the_token_away_from_page_scripts(cookie_client):
    r = cookie_login(cookie_client)
    body = r.json()
    assert body["access_token"] is None and body["token_type"] == "cookie" and len(body["csrf_token"]) >= 20
    cookies = r.headers.get_list("set-cookie")
    session = next(c for c in cookies if c.startswith("avc_session_store_a="))
    csrf = next(c for c in cookies if c.startswith("avc_csrf_store_a="))
    for flag in ("HttpOnly", "SameSite=strict", "Path=/api/stores/store-a"):
        assert flag.lower() in session.lower()
    assert "httponly" not in csrf.lower() and body["csrf_token"] in csrf
    assert "secure" not in session.lower()          # development over http; production adds Secure (below)


def test_cookie_session_reads_work_and_writes_need_csrf(cookie_client):
    csrf = cookie_login(cookie_client).json()["csrf_token"]
    assert cookie_client.get("/api/stores/store-a/me").json()["name"] == "Jordan Lee"
    put = lambda headers: cookie_client.put("/api/stores/store-a/cart/items/lumen-300-headlamp", json={"quantity": 1}, headers=headers)  # noqa: E731
    assert put({}).status_code == 403
    assert put({"X-CSRF-Token": "forged-value-forged-value"}).status_code == 403
    assert put({"X-CSRF-Token": csrf}).status_code == 200


def test_cookie_of_one_store_never_authenticates_the_other(cookie_client):
    cookie_login(cookie_client, "store-a", ALEX, PW_A)
    assert cookie_client.get("/api/stores/store-b/me").status_code == 401      # path-scoped cookie: not even sent
    cookie_login(cookie_client, "store-b", ALEX, PW_B)
    assert cookie_client.get("/api/stores/store-a/me").json()["email"] == cookie_client.get("/api/stores/store-b/me").json()["email"]


def test_logout_revokes_and_clears_cookies(cookie_client):
    csrf = cookie_login(cookie_client).json()["csrf_token"]
    stolen = cookie_client.cookies.get("avc_session_store_a")
    r = cookie_client.post("/api/stores/store-a/auth/logout", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 204
    assert any(c.startswith("avc_session_store_a=") and ("max-age=0" in c.lower() or "expires=" in c.lower()) for c in r.headers.get_list("set-cookie"))
    cookie_client.cookies.set("avc_session_store_a", stolen, path="/api/stores/store-a")      # a copied cookie is now useless
    assert cookie_client.get("/api/stores/store-a/me").status_code == 401


def test_logout_without_csrf_is_refused(cookie_client):
    cookie_login(cookie_client)
    assert cookie_client.post("/api/stores/store-a/auth/logout").status_code == 403
    assert cookie_client.get("/api/stores/store-a/me").status_code == 200


def test_sign_out_everywhere_revokes_every_session(client):
    a = login(client, "store-a", JORDAN, PW_A)
    b = login(client, "store-a", JORDAN, PW_A)
    assert client.post("/api/stores/store-a/auth/logout-all", headers=a).status_code == 204
    assert client.get("/api/stores/store-a/me", headers=a).status_code == 401
    assert client.get("/api/stores/store-a/me", headers=b).status_code == 401


def test_bearer_mode_is_unchanged_and_ignores_cookies(client, cookie_client):
    r = client.post("/api/stores/store-a/auth/login", json={"email": JORDAN, "password": PW_A})
    assert r.json()["token_type"] == "bearer" and r.json()["access_token"] and not r.headers.get_list("set-cookie")
    client.cookies.set("avc_session_store_a", r.json()["access_token"], path="/api/stores/store-a")
    assert client.get("/api/stores/store-a/me").status_code == 401           # cookies are not accepted in bearer mode


def test_production_cookies_are_secure(settings):
    import dataclasses
    with make_client(dataclasses.replace(settings, app_env="production"), auth_cookies=True) as c:
        cookies = cookie_login(c).headers.get_list("set-cookie")
    assert all("secure" in x.lower() for x in cookies if x.startswith("avc_"))

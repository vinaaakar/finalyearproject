"""Registration, sessions (sign-out / revocation) and password reset — all store-scoped."""

import re

from app.notify import MemorySender
from tests.conftest import ALEX, MARIA, PW_A, PW_B, STRONG_PW, db_exec, login, make_client, new_customer


def test_register_signs_in_as_customer(client):
    headers, email = new_customer(client, "store-a", "Riley Park")
    me = client.get("/api/stores/store-a/me", headers=headers).json()
    assert me == {"name": "Riley Park", "email": email, "role": "customer"}


def test_register_cannot_choose_role(client):
    r = client.post("/api/stores/store-a/auth/register",
                    json={"email": "sneaky@example.com", "full_name": "S", "password": STRONG_PW, "role": "agent"})
    assert r.status_code == 422


def test_register_rejects_weak_passwords_without_echo(client):
    for pw in ("short", "password123", "aaaaaaaaaaaa"):
        r = client.post("/api/stores/store-a/auth/register", json={"email": "weak@example.com", "full_name": "W", "password": pw})
        assert r.status_code == 422 and pw not in r.text


def test_password_is_hashed(client, settings):
    _, email = new_customer(client, "store-b")
    stored = db_exec(settings, "store-b", "SELECT password_hash FROM customers WHERE email = %s", [email])[0][0]
    assert stored.startswith("scrypt$") and STRONG_PW not in stored


def test_duplicate_email_in_same_store_rejected_case_insensitive(client):
    r = client.post("/api/stores/store-a/auth/register", json={"email": ALEX.upper(), "full_name": "A", "password": STRONG_PW})
    assert r.status_code == 409


def test_same_email_registers_separately_per_store(client, settings):
    # Maria exists only in Store B; registering her email in Store A creates an independent account.
    r = client.post("/api/stores/store-a/auth/register", json={"email": MARIA, "full_name": "Maria A", "password": STRONG_PW})
    assert r.status_code == 201
    a_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/stores/store-a/orders", headers=a_headers).json()["orders"] == []
    # Her Store B password is unchanged and her Store A token is useless in Store B.
    login(client, "store-b", MARIA, PW_B)
    assert client.get("/api/stores/store-b/orders", headers=a_headers).status_code == 403
    db_exec(settings, "store-a", "DELETE FROM sessions WHERE customer_id IN (SELECT id FROM customers WHERE email = %s)", [MARIA])
    db_exec(settings, "store-a", "DELETE FROM customers WHERE email = %s", [MARIA])


def test_logout_revokes_token(client):
    headers = login(client, "store-a", ALEX, PW_A)
    assert client.get("/api/stores/store-a/me", headers=headers).status_code == 200
    assert client.post("/api/stores/store-a/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/stores/store-a/me", headers=headers).status_code == 401


def test_logout_only_ends_that_session(client):
    first = login(client, "store-a", ALEX, PW_A)
    second = login(client, "store-a", ALEX, PW_A)
    client.post("/api/stores/store-a/auth/logout", headers=first)
    assert client.get("/api/stores/store-a/me", headers=second).status_code == 200


def test_token_without_server_session_rejected(client, settings):
    from app.security import Principal, issue_token
    from app.stores import StoreId

    forged = issue_token(Principal(customer_id=1, store=StoreId.STORE_A, role="agent", name="x", session_id="made-up"),
                         settings.secret_key, 5)
    assert client.get("/api/stores/store-a/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def _reset_token(mailer: MemorySender) -> str:
    store, email = mailer.sent[-1]
    return re.search(r"#token=([A-Za-z0-9_-]+)", email.body).group(1)


def test_password_reset_flow(settings):
    mailer = MemorySender()
    with make_client(settings, mailer=mailer) as c:
        old_session, email = new_customer(c, "store-b")
        r = c.post("/api/stores/store-b/auth/password-reset/request", json={"email": email})
        assert r.status_code == 202
        token = _reset_token(mailer)
        assert mailer.sent[-1][0] == "store-b" and "127.0.0.1:5181/reset-password#token=" in mailer.sent[-1][1].body

        assert c.post("/api/stores/store-b/auth/password-reset/confirm", json={"token": token, "new_password": "Brand-New-Pass-7"}).status_code == 200
        # Existing sessions are signed out, the old password stops working, the new one works.
        assert c.get("/api/stores/store-b/me", headers=old_session).status_code == 401
        assert c.post("/api/stores/store-b/auth/login", json={"email": email, "password": STRONG_PW}).status_code == 401
        login(c, "store-b", email, "Brand-New-Pass-7")
        # Single use.
        assert c.post("/api/stores/store-b/auth/password-reset/confirm", json={"token": token, "new_password": "Another-Pass-88"}).status_code == 400


def test_password_reset_does_not_reveal_accounts(settings):
    mailer = MemorySender()
    with make_client(settings, mailer=mailer) as c:
        known = c.post("/api/stores/store-a/auth/password-reset/request", json={"email": ALEX})
        unknown = c.post("/api/stores/store-a/auth/password-reset/request", json={"email": "nobody-here@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(mailer.sent) == 1


def test_password_reset_token_is_store_scoped(settings):
    mailer = MemorySender()
    with make_client(settings, mailer=mailer) as c:
        c.post("/api/stores/store-a/auth/password-reset/request", json={"email": ALEX})
        token = _reset_token(mailer)
        # Alex also has a Store B account, but a Store A token cannot reset it.
        r = c.post("/api/stores/store-b/auth/password-reset/confirm", json={"token": token, "new_password": "Brand-New-Pass-7"})
        assert r.status_code == 400
        login(c, "store-b", ALEX, PW_B)


def test_expired_reset_token_rejected(settings):
    mailer = MemorySender()
    with make_client(settings, mailer=mailer) as c:
        _, email = new_customer(c, "store-a")
        c.post("/api/stores/store-a/auth/password-reset/request", json={"email": email})
        token = _reset_token(mailer)
        db_exec(settings, "store-a", "UPDATE password_reset_tokens SET expires_at = now() - interval '1 minute'")
        assert c.post("/api/stores/store-a/auth/password-reset/confirm", json={"token": token, "new_password": "Brand-New-Pass-7"}).status_code == 400


def test_reset_tokens_stored_hashed(settings):
    mailer = MemorySender()
    with make_client(settings, mailer=mailer) as c:
        _, email = new_customer(c, "store-a")
        c.post("/api/stores/store-a/auth/password-reset/request", json={"email": email})
        token = _reset_token(mailer)
    hashes = [r[0] for r in db_exec(settings, "store-a", "SELECT token_hash FROM password_reset_tokens")]
    assert token not in hashes and all(len(h) == 64 for h in hashes)

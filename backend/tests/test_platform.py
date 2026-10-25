"""Config validation, security primitives, rate limiting, errors, speech and phone."""

import time

import pytest

from app.config import ConfigError, load_settings
from app.logging_config import redact
from app.security import Principal, TokenError, decode_token, hash_password, issue_token, verify_password
from app.stores import StoreId
from tests.conftest import ALEX, PW_A, make_client

GOOD_ENV = {
    "APP_SECRET_KEY": "x" * 40,
    "STORE_A_DATABASE_URL": "postgresql://a:pw@127.0.0.1:5433/store_a",
    "STORE_B_DATABASE_URL": "postgresql://b:pw@127.0.0.1:5433/store_b",
}


# ---- configuration ------------------------------------------------------------------------
def test_config_valid(tmp_path):
    s = load_settings(GOOD_ENV, env_file=tmp_path / "none")
    assert s.ollama_model == "llama3.2:3b"


@pytest.mark.parametrize("override,needle", [
    ({"APP_SECRET_KEY": "short"}, "APP_SECRET_KEY"),
    ({"APP_SECRET_KEY": "change-me-" + "x" * 40}, "APP_SECRET_KEY"),
    ({"STORE_B_DATABASE_URL": GOOD_ENV["STORE_A_DATABASE_URL"]}, "different"),
    ({"STORE_A_DATABASE_URL": "mysql://x@y/z"}, "STORE_A_DATABASE_URL"),
    ({"RATE_LIMIT_CHAT_PER_MIN": "abc"}, "RATE_LIMIT_CHAT_PER_MIN"),
])
def test_config_errors(tmp_path, override, needle):
    with pytest.raises(ConfigError) as exc:
        load_settings({**GOOD_ENV, **override}, env_file=tmp_path / "none")
    assert needle in str(exc.value)
    assert "pw@" not in str(exc.value)  # values are never echoed


def test_config_missing_required(tmp_path):
    with pytest.raises(ConfigError) as exc:
        load_settings({}, env_file=tmp_path / "none")
    assert "STORE_A_DATABASE_URL is required" in str(exc.value)


# ---- security primitives ------------------------------------------------------------------
def test_password_hashing():
    h = hash_password("pw-123")
    assert verify_password("pw-123", h) and not verify_password("pw-124", h)
    assert "pw-123" not in h


def test_token_roundtrip_and_tamper():
    p = Principal(customer_id=7, store=StoreId.STORE_A, role="customer", name="T")
    tok = issue_token(p, "s" * 40, 5)
    assert decode_token(tok, "s" * 40) == p
    with pytest.raises(TokenError):
        decode_token(tok, "t" * 40)
    with pytest.raises(TokenError):
        decode_token(tok[:-2] + "xx", "s" * 40)


def test_token_expiry(monkeypatch):
    p = Principal(customer_id=7, store=StoreId.STORE_A, role="customer", name="T")
    tok = issue_token(p, "s" * 40, 1)
    monkeypatch.setattr(time, "time", lambda: 10**12)
    with pytest.raises(TokenError):
        decode_token(tok, "s" * 40)


def test_log_redaction():
    line = "Authorization: Bearer abcdefghijklmnopqrstuvwxyz password=hunter2 postgresql://user:secretpw@host/db"
    out = redact(line)
    assert "abcdefghijklmnop" not in out and "hunter2" not in out and "secretpw" not in out


# ---- rate limiting & errors -----------------------------------------------------------------
def test_login_rate_limit(settings):
    with make_client(settings, rate_limit_login_per_min=3) as c:
        codes = [c.post("/api/stores/store-a/auth/login", json={"email": ALEX, "password": "bad"}).status_code for _ in range(4)]
        r = c.post("/api/stores/store-a/auth/login", json={"email": ALEX, "password": PW_A})
    assert codes == [401, 401, 401, 429]
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_chat_rate_limit(settings):
    with make_client(settings, rate_limit_chat_per_min=2) as c:
        codes = [c.post("/api/stores/store-a/chat", json={"message": "hi"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_unknown_route_is_json_404(client):
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_health(client):
    body = client.get("/api/health").json()
    assert body["databases"] == {"store-a": True, "store-b": True}
    assert body["llm"]["enabled"] is False and body["llm"]["mode"] == "rule-based fallback"


# ---- speech -------------------------------------------------------------------------------
def test_speech_capabilities_report_no_server_engine(client):
    body = client.get("/api/speech/capabilities").json()
    assert body["server_stt"]["available"] is False
    assert body["recommended_client_mode"] == "browser"


# ---- phone simulator ----------------------------------------------------------------------
def turn(client, cid, **kw):
    r = client.post(f"/api/phone/simulator/calls/{cid}/turns", json=kw)
    assert r.status_code == 200, r.text
    return r.json()


def test_phone_simulator_is_labelled(client):
    r = client.post("/api/phone/simulator/store-a/calls").json()
    assert r["simulated"] is True and "SIMULATION" in r["notice"]
    assert "Summit Trail" in r["say"]


def test_phone_order_status_requires_verification(client):
    cid = client.post("/api/phone/simulator/store-a/calls").json()["call_id"]
    assert "order number" in turn(client, cid, speech="I want to check my order")["say"]
    assert "ZIP" in turn(client, cid, digits="10001")["say"]
    wrong = turn(client, cid, digits="99999")
    assert "don't match" in wrong["say"] and "shipped" not in wrong["say"]
    turn(client, cid, speech="SA-10001")
    ok = turn(client, cid, speech="8 0 3 0 2")
    assert "SA-10001 is shipped" in ok["say"]


def test_phone_locks_after_repeated_failures(client):
    cid = client.post("/api/phone/simulator/store-b/calls").json()["call_id"]
    turn(client, cid, speech="track order BB-20001")
    for _ in range(2):
        turn(client, cid, digits="00000")
        turn(client, cid, digits="20001")
    final = turn(client, cid, digits="00000")
    assert final["hang_up"] is True
    assert client.post(f"/api/phone/simulator/calls/{cid}/turns", json={"speech": "hello"}).status_code == 404


def test_phone_answers_general_questions_and_goodbye(client):
    cid = client.post("/api/phone/simulator/store-b/calls").json()["call_id"]
    assert "$4.99" in turn(client, cid, speech="how much is shipping")["say"]
    assert turn(client, cid, speech="that's all, bye")["hang_up"] is True

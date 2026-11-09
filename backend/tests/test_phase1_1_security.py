"""Phase 1.1 — production security separation: response headers, API docs gating, private-response caching,
demo-data seeding guard, and rate-limit identity behind a trusted proxy."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import load_settings
from app.seed import demo_seeding_refusal
from tests.conftest import make_client

STRICT_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
PROD_ENV = {"APP_ENV": "production", "APP_SECRET_KEY": "x" * 48, "CORS_ORIGINS": "https://shop.example",
            "STORE_A_DATABASE_URL": "postgresql://a:b@127.0.0.1:1/store_a", "STORE_B_DATABASE_URL": "postgresql://a:b@127.0.0.1:1/store_b"}


@pytest.mark.parametrize("path", ["/api/health", "/api/stores/store-a/products", "/api/stores/store-a/products/nope",
                                  "/api/stores/store-c/products"])
def test_every_api_response_carries_security_headers(client, path):
    h = client.get(path).headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "no-referrer"
    assert h["Content-Security-Policy"] == STRICT_CSP
    assert "microphone=()" in h["Permissions-Policy"]
    assert "Strict-Transport-Security" not in h          # development: no HSTS on plain http


def test_hsts_only_in_production(settings):
    with make_client(settings, app_env="production") as c:
        assert c.get("/api/health").headers["Strict-Transport-Security"].startswith("max-age=31536000")


def test_private_responses_are_never_cached(client):
    assert client.get("/api/stores/store-a/me").headers["Cache-Control"] == "no-store"            # 401 too
    assert client.post("/api/stores/store-a/chat", json={"message": "hi"}).headers["Cache-Control"] == "no-store"
    assert client.get("/api/stores/store-a/cart").headers["Cache-Control"] == "no-store"
    assert "Cache-Control" not in client.get("/api/stores/store-a/products").headers                # public catalogue


def test_api_docs_available_in_development_without_csp(client):
    r = client.get("/docs")
    assert r.status_code == 200 and "Content-Security-Policy" not in r.headers   # the docs page loads its own scripts
    assert client.get("/openapi.json").status_code == 200


def test_api_docs_hidden_when_disabled(settings):
    with make_client(settings, api_docs_enabled=False) as c:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert c.get(path).status_code == 404, path


def test_production_defaults_are_safe():
    s = load_settings(PROD_ENV, env_file=Path("/nonexistent"))
    assert s.api_docs_enabled is False and s.phone_simulator_enabled is False and s.trusted_proxies == ()
    assert load_settings({**PROD_ENV, "API_DOCS_ENABLED": "true"}, env_file=Path("/nonexistent")).api_docs_enabled is True
    assert load_settings({**PROD_ENV, "TRUSTED_PROXIES": "10.0.0.1, 10.0.0.2"}, env_file=Path("/nonexistent")).trusted_proxies == ("10.0.0.1", "10.0.0.2")


@pytest.mark.parametrize("env, reset, allow, refused", [
    ("development", False, False, False),
    ("development", True, False, False),
    ("production", False, False, True),     # published demo passwords
    ("production", False, True, False),     # explicit disposable demo
    ("production", True, True, True),       # --reset never outside development
    ("staging", True, False, True),
])
def test_demo_seeding_guard(env, reset, allow, refused):
    assert (demo_seeding_refusal(env, reset, allow) is not None) is refused


def _bad_logins(c, n, headers=None):
    return [c.post("/api/stores/store-a/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"},
                   headers=headers or {}).status_code for _ in range(n)]


def test_rate_limit_identity_ignores_spoofed_forwarded_for(client):
    limit = client.app.state.settings.rate_limit_login_per_min
    codes = [_bad_logins(client, 1, {"X-Forwarded-For": f"203.0.113.{i}"})[0] for i in range(limit + 1)]
    assert codes[-1] == 429      # rotating a spoofed header does not escape the limit


def test_rate_limit_is_per_client_behind_a_trusted_proxy(settings):
    with make_client(settings, trusted_proxies=("testclient",)) as c:
        limit = c.app.state.settings.rate_limit_login_per_min
        assert _bad_logins(c, limit + 1, {"X-Forwarded-For": "203.0.113.1"})[-1] == 429
        assert _bad_logins(c, 1, {"X-Forwarded-For": "203.0.113.2"}) == [401]   # a different customer is unaffected


def test_unhandled_errors_still_get_headers_and_no_details(settings):
    with make_client(settings) as c:
        def boom():
            raise RuntimeError("secret internal detail")
        c.app.add_api_route("/api/_test_boom", boom)
        c.app.router.routes.insert(0, c.app.router.routes.pop())
        r = c.get("/api/_test_boom")
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error"
    assert "secret internal detail" not in r.text
    assert r.headers["Content-Security-Policy"] == STRICT_CSP and r.headers["X-Frame-Options"] == "DENY"

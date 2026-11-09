"""Test fixtures. Tests run against the dedicated *_test databases (never the dev
databases), which are migrated and reseeded with synthetic data once per session."""

from __future__ import annotations

import dataclasses
from urllib.parse import urlparse, urlunparse

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from app.migrate import migrate_database
from app.notify import MemorySender
from app.ratelimit import limiter
from app.seed import AGENT_PASSWORD, DEMO_PASSWORDS, seed_store
from app.stores import StoreId


def _to_test_db(url: str) -> str:
    p = urlparse(url)
    return urlunparse(p._replace(path=p.path.rstrip("/") + "_test"))


@pytest.fixture(scope="session")
def settings():
    base = load_settings()
    urls = {k: _to_test_db(v) for k, v in base.store_database_urls.items()}
    # Speech engines are pinned off so results don't depend on the local .env; tests that need an engine install one.
    return dataclasses.replace(base, store_database_urls=urls, llm_enabled=False, speech_stt="none", speech_tts="none")


@pytest.fixture(scope="session", autouse=True)
def test_databases(settings):
    for store in StoreId:
        url = settings.store_database_urls[store.value]
        migrate_database(url)
        seed_store(store, url, reset=True)
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    limiter.reset()
    yield
    limiter.reset()


def make_client(settings, llm=False, mailer=None, **overrides) -> TestClient:
    app = create_app(dataclasses.replace(settings, **overrides) if overrides else settings, llm=llm, mailer=mailer or MemorySender())
    return TestClient(app)


@pytest.fixture
def client(settings):
    with make_client(settings) as c:
        yield c


def login(client: TestClient, store: str, email: str, password: str) -> dict[str, str]:
    r = client.post(f"/api/stores/{store}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# Synthetic demo accounts (see app/seed.py)
ALEX = "alex.rivera@example.com"           # exists separately in BOTH stores
JORDAN = "jordan.lee@example.com"          # Store A only
MARIA = "maria.gomez@example.com"          # Store B only
AGENT_A = "agent@summittrail.example.com"
AGENT_B = "agent@bloomandbrew.example.com"
PW_A = DEMO_PASSWORDS[StoreId.STORE_A]
PW_B = DEMO_PASSWORDS[StoreId.STORE_B]
PW_AGENT = AGENT_PASSWORD


# ---- helpers for commerce tests ---------------------------------------------------------------
import itertools
import uuid

import psycopg

_seq = itertools.count()
STRONG_PW = "Correct-Horse-42"


def db_exec(settings, store: str, sql: str, params=None):
    """Direct SQL against a *test* store database (for arranging stock, inspecting rows)."""
    with psycopg.connect(settings.store_database_urls[store]) as conn:
        cur = conn.execute(sql, params or [])
        return cur.fetchall() if cur.description else cur.rowcount


def set_stock(settings, store: str, slug: str, qty: int) -> None:
    db_exec(settings, store, "UPDATE products SET stock_qty = %s WHERE slug = %s", [qty, slug])


def new_customer(client: TestClient, store: str, name: str = "Test Shopper") -> tuple[dict[str, str], str]:
    email = f"shopper{next(_seq)}-{uuid.uuid4().hex[:6]}@example.com"
    r = client.post(f"/api/stores/{store}/auth/register", json={"email": email, "full_name": name, "password": STRONG_PW})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, email


def idem() -> dict[str, str]:
    return {"Idempotency-Key": uuid.uuid4().hex}


ADDRESS_A = {"full_name": "Test Shopper", "line1": "1 Trail Way", "city": "Boulder", "region": "CO", "postal_code": "80302"}
ADDRESS_B = {"full_name": "Test Shopper", "line1": "2 Brew St", "city": "Chicago", "region": "IL", "postal_code": "60614"}

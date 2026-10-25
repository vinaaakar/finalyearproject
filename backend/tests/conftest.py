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
    return dataclasses.replace(base, store_database_urls=urls, llm_enabled=False)


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


def make_client(settings, llm=False, **overrides) -> TestClient:
    app = create_app(dataclasses.replace(settings, **overrides) if overrides else settings, llm=llm)
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

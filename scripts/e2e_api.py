#!/usr/bin/env python3
"""Isolated API for the Playwright browser tests (started and stopped by frontend/playwright.config.js).

Safety:
- Connects ONLY to the `*_test` databases (the same `<dev url>_test` rule as backend/tests/conftest.py) and refuses to
  start otherwise. Never the development databases.
- Never migrates, seeds or resets anything: it refuses to start if a test database's applied migrations differ from
  backend/migrations/*.sql. Browser tests only add synthetic rows (a new test customer, a cart, an order that the test
  cancels again) through the normal API, like the backend suite does.
- Language model and speech engines off (deterministic, no Ollama/whisper load); runs on its own port, so the live
  API on :8000 is never touched.

Usage: backend/.venv/bin/python scripts/e2e_api.py [--port 18000]
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def test_url(url: str) -> str:
    p = urlparse(url)
    return urlunparse(p._replace(path=p.path.rstrip("/") + "_test"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18000)
    args = ap.parse_args()

    import psycopg
    import uvicorn

    from app.config import load_settings
    from app.logging_config import configure_logging
    from app.main import create_app

    base = load_settings()
    urls = {k: test_url(v) for k, v in base.store_database_urls.items()}
    for store, url in urls.items():
        name = urlparse(url).path.lstrip("/")
        if not name.endswith("_test"):
            print(f"refusing: {store} would use database {name!r}, not a *_test database", file=sys.stderr)
            return 2
    expected = sorted(p.stem for p in (ROOT / "backend" / "migrations").glob("*.sql"))
    for store, url in urls.items():
        with psycopg.connect(url) as conn:   # read-only check
            applied = sorted(r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall())
        if applied != expected:
            print(f"refusing: {store} test database is at {applied}, expected {expected} "
                  "(run the backend test suite to migrate the test databases; this launcher never migrates)", file=sys.stderr)
            return 3
    # Rate limits are raised for this process only: one browser run registers several synthetic customers and makes
    # many requests from one address within a minute. The live API keeps its own limits.
    # AVC_E2E_SPEECH=1 keeps the local speech engines (whisper.cpp, macOS voices) for the voice browser tests.
    speech = os.environ.get("AVC_E2E_SPEECH") == "1"
    settings = dataclasses.replace(base, store_database_urls=urls, llm_enabled=False,
                                   speech_stt=base.speech_stt if speech else "none", speech_tts=base.speech_tts if speech else "none",
                                   phone_simulator_enabled=False, rate_limit_login_per_min=600,
                                   rate_limit_chat_per_min=600, rate_limit_default_per_min=6000,
                                   auth_cookies=os.environ.get("AVC_E2E_AUTH_COOKIES") == "1")
    configure_logging()
    print(f"E2E API on 127.0.0.1:{args.port} using {sorted(urlparse(u).path.lstrip('/') for u in urls.values())}", flush=True)
    uvicorn.run(create_app(settings, llm=False), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Apply SQL migrations in backend/migrations to every store database.

Usage: python -m app.migrate
Each store database tracks its own applied versions in `schema_migrations`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg

from .config import load_settings
from .stores import StoreId

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
log = logging.getLogger("migrate")


def migrate_database(url: str) -> list[str]:
    applied_now = []
    with psycopg.connect(url) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
        done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        conn.commit()
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.stem
            if version in done:
                continue
            with conn.transaction():
                conn.execute(path.read_text())
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", [version])
            applied_now.append(version)
    return applied_now


def migrate_all(database_urls: dict[str, str]) -> None:
    for store in StoreId:
        applied = migrate_database(database_urls[store.value])
        print(f"{store.value}: {'applied ' + ', '.join(applied) if applied else 'up to date'}")


if __name__ == "__main__":
    migrate_all(load_settings().store_database_urls)

"""One connection pool per store database.

`store_connection(store_id)` is the only way application code obtains a database
connection, and it always returns a connection to that store's own database,
authenticated as that store's own database role.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .stores import StoreId

_pools: dict[StoreId, ConnectionPool] = {}


def init_pools(database_urls: dict[str, str]) -> None:
    close_pools()
    for store in StoreId:
        _pools[store] = ConnectionPool(
            database_urls[store.value],
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row, "autocommit": False},
            open=True,
            name=f"pool-{store.value}",
        )


def close_pools() -> None:
    for pool in _pools.values():
        pool.close()
    _pools.clear()


@contextmanager
def store_connection(store: StoreId) -> Iterator[psycopg.Connection]:
    if store not in _pools:
        raise RuntimeError("Database pools are not initialised")
    with _pools[store].connection() as conn:
        yield conn


def check_store_db(store: StoreId) -> bool:
    try:
        with store_connection(store) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False

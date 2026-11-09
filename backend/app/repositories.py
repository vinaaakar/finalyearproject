"""Controlled, parameterised database access.

Every query the application can run lives here, or in `commerce.py` / `payments/`
for the multi-step cart, checkout and payment transactions. Callers (HTTP routes,
the AI assistant, the phone flow) pass a validated StoreId and typed arguments;
nothing else builds SQL, and the language model never sees or writes SQL.
"""

from __future__ import annotations

from typing import Any

from .db import store_connection
from .stores import StoreId

_PRODUCT_COLS = "id, sku, slug, name, category, description, price_cents, stock_qty, emoji"
_ORDER_COLS = (
    "o.id, o.order_number, o.customer_id, o.status, o.carrier, o.tracking_number, "
    "o.estimated_delivery, o.total_cents, o.placed_at, o.updated_at, o.subtotal_cents, o.shipping_cents, o.shipping_method"
)


def get_store_profile(store: StoreId) -> dict[str, Any] | None:
    with store_connection(store) as conn:
        return conn.execute("SELECT name, support_email, support_hours, currency FROM store_profile WHERE id = 1").fetchone()


def get_policies(store: StoreId, language: str = "en") -> dict[str, dict[str, str]]:
    """Policy text in the requested language (ta / hi), falling back to English where a translation is missing."""
    with store_connection(store) as conn:
        rows = conn.execute("SELECT topic, summary, details, summary_ta, details_ta, summary_hi, details_hi FROM policies ORDER BY topic").fetchall()
    out = {}
    for r in rows:
        s, d = (r.get(f"summary_{language}"), r.get(f"details_{language}")) if language in ("ta", "hi") else (None, None)
        out[r["topic"]] = {"summary": s or r["summary"], "details": d or r["details"]}
    return out


def list_categories(store: StoreId) -> list[str]:
    with store_connection(store) as conn:
        return [r["category"] for r in conn.execute("SELECT DISTINCT category FROM products ORDER BY category").fetchall()]


def list_products(store: StoreId, category: str | None = None, query: str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    clauses, params = [], []
    if category:
        clauses.append("category = %s")
        params.append(category)
    if query:
        clauses.append("(name ILIKE %s OR description ILIKE %s OR category ILIKE %s)")
        like = f"%{_escape_like(query)}%"
        params += [like, like, like]
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with store_connection(store) as conn:
        return conn.execute(
            f"SELECT {_PRODUCT_COLS} FROM products {where} ORDER BY name LIMIT %s OFFSET %s",
            [*params, limit, offset],
        ).fetchall()


def get_product_by_slug(store: StoreId, slug: str) -> dict[str, Any] | None:
    with store_connection(store) as conn:
        return conn.execute(f"SELECT {_PRODUCT_COLS} FROM products WHERE slug = %s", [slug]).fetchone()


def search_products_by_terms(store: StoreId, terms: list[str], limit: int = 5, max_price_cents: int | None = None) -> list[dict[str, Any]]:
    """Rank products by how many of the given terms appear in name/category/description (in-stock first on ties)."""
    terms = [t for t in terms if t][:8]
    if not terms:
        return []
    score_parts, params = [], []
    for term in terms:
        like = f"%{_escape_like(term)}%"
        score_parts.append("(CASE WHEN name ILIKE %s THEN 3 ELSE 0 END + CASE WHEN category ILIKE %s THEN 2 ELSE 0 END + CASE WHEN description ILIKE %s THEN 1 ELSE 0 END)")
        params += [like, like, like]
    score = " + ".join(score_parts)
    with store_connection(store) as conn:
        rows = conn.execute(
            f"SELECT {_PRODUCT_COLS}, score FROM (SELECT {_PRODUCT_COLS}, ({score}) AS score FROM products) s "
            "WHERE score > 0 AND (%s::int IS NULL OR price_cents <= %s::int) ORDER BY score DESC, (stock_qty > 0) DESC, name LIMIT %s",
            [*params, max_price_cents, max_price_cents, limit],
        ).fetchall()
    # Drop weak partial matches (e.g. "rain" inside a tent's "rainfly") when a strong match exists.
    return [r for r in rows if r["score"] * 2 >= rows[0]["score"]] if rows else rows


def recommend_products(store: StoreId, max_price_cents: int | None = None, limit: int = 3) -> list[dict[str, Any]]:
    """In-stock products from this store's catalog, optionally within a budget (most expensive that fits first)."""
    with store_connection(store) as conn:
        return conn.execute(
            f"SELECT {_PRODUCT_COLS} FROM products WHERE stock_qty > 0 AND (%s::int IS NULL OR price_cents <= %s::int) "
            "ORDER BY price_cents DESC, name LIMIT %s",
            [max_price_cents, max_price_cents, limit],
        ).fetchall()


def get_customer_by_email(store: StoreId, email: str) -> dict[str, Any] | None:
    with store_connection(store) as conn:
        return conn.execute(
            "SELECT id, email, full_name, password_hash, role FROM customers WHERE lower(email) = lower(%s)", [email]
        ).fetchone()


def get_customer_by_id(store: StoreId, customer_id: int) -> dict[str, Any] | None:
    with store_connection(store) as conn:
        return conn.execute("SELECT id, email, full_name, role FROM customers WHERE id = %s", [customer_id]).fetchone()


def list_orders_for_customer(store: StoreId, customer_id: int) -> list[dict[str, Any]]:
    with store_connection(store) as conn:
        orders = conn.execute(
            f"SELECT {_ORDER_COLS} FROM orders o WHERE o.customer_id = %s ORDER BY o.placed_at DESC", [customer_id]
        ).fetchall()
        return [_attach_items(conn, o) for o in orders]


def get_order_for_customer(store: StoreId, order_number: str, customer_id: int) -> dict[str, Any] | None:
    """Returns the order only if it belongs to this customer; otherwise None (no existence leak)."""
    with store_connection(store) as conn:
        order = conn.execute(
            f"SELECT {_ORDER_COLS} FROM orders o WHERE o.order_number = %s AND o.customer_id = %s",
            [order_number.upper(), customer_id],
        ).fetchone()
        return _attach_items(conn, order) if order else None


def get_order_by_number(store: StoreId, order_number: str) -> dict[str, Any] | None:
    """Staff-only lookup. Callers must have verified an agent role for this store."""
    with store_connection(store) as conn:
        order = conn.execute(f"SELECT {_ORDER_COLS} FROM orders o WHERE o.order_number = %s", [order_number.upper()]).fetchone()
        return _attach_items(conn, order) if order else None


def list_recent_orders(store: StoreId, limit: int = 50) -> list[dict[str, Any]]:
    with store_connection(store) as conn:
        return conn.execute(
            f"SELECT {_ORDER_COLS}, c.full_name AS customer_name FROM orders o JOIN customers c ON c.id = o.customer_id "
            "ORDER BY o.placed_at DESC LIMIT %s",
            [limit],
        ).fetchall()


def verify_order_for_phone(store: StoreId, order_number: str, postal_code: str) -> dict[str, Any] | None:
    """Phone verification: order number plus the shipping postal code must both match."""
    with store_connection(store) as conn:
        order = conn.execute(
            f"SELECT {_ORDER_COLS} FROM orders o WHERE o.order_number = %s AND upper(replace(o.shipping_postal_code, ' ', '')) = %s",
            [order_number.upper(), postal_code.upper().replace(" ", "")],
        ).fetchone()
        return _attach_items(conn, order) if order else None


def _attach_items(conn, order: dict[str, Any]) -> dict[str, Any]:
    order["items"] = conn.execute(
        "SELECT p.name, p.slug, i.quantity, i.unit_price_cents FROM order_items i JOIN products p ON p.id = i.product_id "
        "WHERE i.order_id = %s ORDER BY i.id",
        [order["id"]],
    ).fetchall()
    return order


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---- accounts: registration, sessions, password reset ------------------------------------------
def create_customer(store: StoreId, email: str, full_name: str, password_hash: str) -> dict[str, Any] | None:
    """Creates a customer (never an agent). Returns None if the email is already registered in this store."""
    with store_connection(store) as conn:
        return conn.execute(
            "INSERT INTO customers (email, full_name, password_hash, role) VALUES (lower(%s), %s, %s, 'customer') "
            "ON CONFLICT DO NOTHING RETURNING id, email, full_name, role",
            [email, full_name, password_hash],
        ).fetchone()


def create_session(store: StoreId, customer_id: int, session_hash: str, ttl_minutes: int) -> None:
    with store_connection(store) as conn:
        conn.execute(
            "INSERT INTO sessions (id_hash, customer_id, expires_at) VALUES (%s, %s, now() + make_interval(mins => %s))",
            [session_hash, customer_id, ttl_minutes],
        )


def session_is_active(store: StoreId, session_hash: str, customer_id: int) -> bool:
    with store_connection(store) as conn:
        return conn.execute(
            "SELECT 1 FROM sessions WHERE id_hash = %s AND customer_id = %s AND revoked_at IS NULL AND expires_at > now()",
            [session_hash, customer_id],
        ).fetchone() is not None


def revoke_session(store: StoreId, session_hash: str) -> None:
    with store_connection(store) as conn:
        conn.execute("UPDATE sessions SET revoked_at = now() WHERE id_hash = %s AND revoked_at IS NULL", [session_hash])


def create_password_reset(store: StoreId, customer_id: int, token_hash: str, ttl_minutes: int) -> None:
    """Stores a new reset token hash and invalidates any earlier unused tokens for this customer."""
    with store_connection(store) as conn, conn.transaction():
        conn.execute("UPDATE password_reset_tokens SET used_at = now() WHERE customer_id = %s AND used_at IS NULL", [customer_id])
        conn.execute(
            "INSERT INTO password_reset_tokens (customer_id, token_hash, expires_at) VALUES (%s, %s, now() + make_interval(mins => %s))",
            [customer_id, token_hash, ttl_minutes],
        )


def consume_password_reset(store: StoreId, token_hash: str, new_password_hash: str) -> int | None:
    """Single-use: sets the new password, marks the token used and signs out every session.
    Returns the customer id, or None if the token is unknown, used or expired."""
    with store_connection(store) as conn, conn.transaction():
        row = conn.execute(
            "SELECT id, customer_id FROM password_reset_tokens WHERE token_hash = %s AND used_at IS NULL AND expires_at > now() FOR UPDATE",
            [token_hash],
        ).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE password_reset_tokens SET used_at = now() WHERE id = %s", [row["id"]])
        conn.execute("UPDATE customers SET password_hash = %s WHERE id = %s", [new_password_hash, row["customer_id"]])
        conn.execute("UPDATE sessions SET revoked_at = now() WHERE customer_id = %s AND revoked_at IS NULL", [row["customer_id"]])
        return row["customer_id"]


def get_shipping_rates(store: StoreId) -> dict[str, Any]:
    with store_connection(store) as conn:
        return conn.execute(
            "SELECT currency, standard_shipping_cents, free_shipping_min_cents, expedited_shipping_cents FROM store_profile WHERE id = 1"
        ).fetchone() or {"currency": "USD", "standard_shipping_cents": 0, "free_shipping_min_cents": None, "expedited_shipping_cents": None}

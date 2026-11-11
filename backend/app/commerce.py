"""Cart, checkout and payment flows.

Rules enforced here (never by the browser):
- Prices and stock always come from `products`; the cart stores only product ids and quantities.
- Totals (subtotal, shipping, total) are computed on the server from the store's own shipping rates.
- Checkout re-checks stock and prices with the product rows locked, then creates the order, its
  items and the stock decrement in ONE transaction. An Idempotency-Key makes repeated submissions
  return the original order instead of creating another.
- An order becomes paid only after the server asks the payment provider for the payment status.

Each store has its own database, so a cart, order or payment from one store cannot even be
addressed from the other.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import psycopg

from . import repositories as repo
from .db import store_connection
from .order_state import ConcurrentChange, InvalidTransition, record_history, transition_order, transition_payment
from .payments.base import PaymentProvider
from .stores import ORDER_PREFIX, SHIPPING_EXCLUDED_REGIONS, StoreId

log = logging.getLogger(__name__)

MAX_LINE_QTY = 10
MAX_CART_LINES = 30


class CommerceError(Exception):
    def __init__(self, status: int, message: str, code: str = "commerce_error", details: list | None = None):
        super().__init__(message)
        self.status, self.message, self.code, self.details = status, message, code, details


@dataclass(frozen=True)
class CartOwner:
    """A signed-in customer, or a guest identified by the hash of their cart token."""

    customer_id: int | None = None
    guest_hash: str | None = None


def money(cents: int, currency: str = "USD") -> str:
    # One formatter for every currency (app/markets.py); USD output is unchanged ("$1,249.99").
    from .markets import format_money
    return format_money(cents, currency)


# ---- shipping ------------------------------------------------------------------------------
def shipping_options(rates: dict[str, Any] | None, subtotal: int) -> list[dict[str, Any]]:
    """Options for one destination's rates (shipping_zones.rates_for). None = no rates for that destination: no options,
    never a guessed or US price."""
    if rates is None:
        return []
    cur = (rates.get("currency") or "USD").strip()   # the rates' own currency (INR for India zones)
    free_min = rates["free_shipping_min_cents"]
    standard = 0 if subtotal == 0 or (free_min is not None and subtotal >= free_min) else rates["standard_shipping_cents"]
    options = [{"method": "standard", "label": rates.get("standard_label", "Standard"), "cents": standard, "price": money(standard, cur)}]
    if rates["expedited_shipping_cents"] is not None:
        options.append({"method": "expedited", "label": rates.get("expedited_label", "Expedited (2-day)"),
                        "cents": rates["expedited_shipping_cents"], "price": money(rates["expedited_shipping_cents"], cur)})
    return options


def shipping_cost(rates: dict[str, Any], subtotal: int, method: str) -> int:
    for opt in shipping_options(rates, subtotal):
        if opt["method"] == method:
            return opt["cents"]
    raise CommerceError(422, "That shipping method is not available in this store.", "invalid_shipping_method")


# ---- cart ------------------------------------------------------------------------------------
def _find_cart(conn, owner: CartOwner, create: bool = False) -> int | None:
    if owner.customer_id is not None:
        sql, args = "SELECT id FROM carts WHERE customer_id = %s AND status = 'open'", [owner.customer_id]
    elif owner.guest_hash:
        sql, args = "SELECT id FROM carts WHERE guest_token_hash = %s AND customer_id IS NULL AND status = 'open'", [owner.guest_hash]
    else:
        return None
    row = conn.execute(sql, args).fetchone()
    if row or not create:
        return row["id"] if row else None
    if owner.customer_id is not None:
        conn.execute(
            "INSERT INTO carts (customer_id) VALUES (%s) ON CONFLICT (customer_id) WHERE status = 'open' AND customer_id IS NOT NULL DO NOTHING",
            [owner.customer_id],
        )
    else:
        conn.execute("INSERT INTO carts (guest_token_hash) VALUES (%s) ON CONFLICT (guest_token_hash) DO NOTHING", [owner.guest_hash])
    return conn.execute(sql, args).fetchone()["id"]


def _cart_lines(conn, cart_id: int | None, lock_products: bool = False) -> list[dict[str, Any]]:
    if cart_id is None:
        return []
    # Products are locked in id order so concurrent checkouts cannot deadlock.
    return conn.execute(
        "SELECT p.id AS product_id, p.slug, p.name, p.emoji, p.price_cents, p.stock_qty, ci.quantity "
        "FROM cart_items ci JOIN products p ON p.id = ci.product_id WHERE ci.cart_id = %s ORDER BY p.id"
        + (" FOR UPDATE OF p" if lock_products else ""),
        [cart_id],
    ).fetchall()


def _line_problem(line: dict[str, Any]) -> str | None:
    if line["stock_qty"] <= 0:
        return f"{line['name']} is out of stock."
    if line["quantity"] > line["stock_qty"]:
        return f"Only {line['stock_qty']} of {line['name']} left."
    return None


_US_RATES = object()   # get_cart default: the store's own (US) rates, exactly as before country-aware checkout

SHIPPING_UNCONFIRMED = "Shipping to this address isn't available yet: the store hasn't set delivery rates for it, so the order can't be placed."
PRICES_UNCONFIRMED = "Prices in {currency} haven't been set for {what} yet, so an order can't be placed. Prices are never converted from another currency."


def _priced(store: StoreId, conn, lines: list[dict[str, Any]], country: str) -> tuple[str, list[dict[str, Any]]]:
    """The lines priced in the destination's currency (app/pricing.py). The catalogue currency uses products.price_cents;
    any other uses only owner-approved prices — a line without one gets price_cents None (never converted)."""
    from .pricing import base_currency, currency_for_country, prices_for
    currency = currency_for_country(store, country)
    if currency == base_currency(store):
        return currency, lines
    prices = prices_for(store, currency, lines, conn)
    return currency, [{**ln, "price_cents": prices.get(ln["product_id"])} for ln in lines]


def _view(lines: list[dict[str, Any]], rates: dict[str, Any] | None, method: str = "standard",
          country: str = "US", currency: str | None = None) -> dict[str, Any]:
    currency = currency or (rates or {}).get("currency") or "USD"
    if rates is not None and (rates.get("currency") or currency) != currency:
        rates = None            # rates in another currency are never applied (no conversion)
    unpriced = [ln["name"] for ln in lines if ln["price_cents"] is None]
    items, problems, subtotal = [], [], 0
    for ln in lines:
        problem = _line_problem(ln)
        line_total = None if ln["price_cents"] is None else ln["price_cents"] * ln["quantity"]
        subtotal += line_total or 0
        if problem:
            problems.append(problem)
        items.append({
            "slug": ln["slug"], "name": ln["name"], "emoji": ln["emoji"], "quantity": ln["quantity"],
            "unit_price_cents": ln["price_cents"], "unit_price": None if ln["price_cents"] is None else money(ln["price_cents"], currency),
            "line_total_cents": line_total, "line_total": None if line_total is None else money(line_total, currency),
            "price_available": ln["price_cents"] is not None,
            "stock_qty": ln["stock_qty"], "max_quantity": max(0, min(MAX_LINE_QTY, ln["stock_qty"])), "problem": problem,
        })
    if unpriced:
        # No approved price in this currency for some items: no amounts at all (a partial or converted total would mislead).
        what = "these items" if len(unpriced) < len(lines) else ("this item" if len(lines) == 1 else "the items in your cart")
        return {
            "items": items, "item_count": sum(i["quantity"] for i in items), "currency": currency, "prices_available": False,
            "price_problem": PRICES_UNCONFIRMED.format(currency=currency, what=what), "unpriced_items": unpriced,
            "subtotal_cents": None, "subtotal": None,
            "shipping_method": method, "shipping_cents": None, "shipping": None, "shipping_available": rates is not None,
            "shipping_problem": None if rates is not None else SHIPPING_UNCONFIRMED, "shipping_country": country,
            "shipping_options": [], "total_cents": None, "total": None, "total_excludes_shipping": True,
            "problems": problems, "can_checkout": False,
        }
    if rates is None:
        # No rates for this destination: the total shown is the goods only, and checkout is refused.
        return {
            "items": items, "item_count": sum(i["quantity"] for i in items),
            "subtotal_cents": subtotal, "subtotal": money(subtotal, currency),
            "shipping_method": method, "shipping_cents": None, "shipping": None, "shipping_available": False,
            "shipping_problem": SHIPPING_UNCONFIRMED, "shipping_country": country,
            "shipping_options": [], "total_cents": subtotal, "total": money(subtotal, currency), "total_excludes_shipping": True,
            "currency": currency, "prices_available": True, "problems": problems, "can_checkout": False,
        }
    shipping = shipping_cost(rates, subtotal, method) if items else 0
    total = subtotal + shipping
    return {
        "items": items, "item_count": sum(i["quantity"] for i in items),
        "subtotal_cents": subtotal, "subtotal": money(subtotal, currency),
        "shipping_method": method, "shipping_cents": shipping, "shipping": money(shipping, currency), "shipping_available": True,
        "shipping_country": rates.get("country", "US"),
        "shipping_options": shipping_options(rates, subtotal), "total_cents": total, "total": money(total, currency),
        "currency": currency, "prices_available": True, "problems": problems, "can_checkout": bool(items) and not problems,
    }


def get_cart(store: StoreId, owner: CartOwner, method: str = "standard", rates: Any = _US_RATES, country: str = "US") -> dict[str, Any]:
    """`rates`: a destination's rates (shipping_zones.rates_for), None for a destination without rates, or omitted for the
    store's US rates (cart page, assistant, US checkout — unchanged)."""
    if rates is _US_RATES:
        rates = repo.get_shipping_rates(store)
    with store_connection(store) as conn:
        currency, lines = _priced(store, conn, _cart_lines(conn, _find_cart(conn, owner)), country)
        return _view(lines, rates, method, country, currency)


def set_item(store: StoreId, owner: CartOwner, slug: str, quantity: int, *, add: bool = False) -> dict[str, Any]:
    """Set (or with add=True, increase) a line's quantity after validating it against the database."""
    with store_connection(store) as conn, conn.transaction():
        product = conn.execute("SELECT id, name, stock_qty FROM products WHERE slug = %s", [slug]).fetchone()
        if product is None:
            raise CommerceError(404, "Product not found.", "not_found")
        cart_id = _find_cart(conn, owner, create=quantity > 0)
        current = 0
        if cart_id is not None:
            row = conn.execute("SELECT quantity FROM cart_items WHERE cart_id = %s AND product_id = %s FOR UPDATE", [cart_id, product["id"]]).fetchone()
            current = row["quantity"] if row else 0
        target = current + quantity if add else quantity
        if target <= 0:
            if cart_id is not None:
                conn.execute("DELETE FROM cart_items WHERE cart_id = %s AND product_id = %s", [cart_id, product["id"]])
        else:
            if product["stock_qty"] <= 0:
                raise CommerceError(409, f"{product['name']} is out of stock.", "out_of_stock")
            if target > MAX_LINE_QTY:
                raise CommerceError(409, f"You can buy up to {MAX_LINE_QTY} of each item.", "quantity_limit")
            if target > product["stock_qty"]:
                raise CommerceError(409, f"Only {product['stock_qty']} of {product['name']} left.", "insufficient_stock")
            if current == 0:
                lines = conn.execute("SELECT count(*) AS n FROM cart_items WHERE cart_id = %s", [cart_id]).fetchone()["n"]
                if lines >= MAX_CART_LINES:
                    raise CommerceError(409, "Your cart is full.", "cart_full")
            conn.execute(
                "INSERT INTO cart_items (cart_id, product_id, quantity) VALUES (%s, %s, %s) "
                "ON CONFLICT (cart_id, product_id) DO UPDATE SET quantity = EXCLUDED.quantity",
                [cart_id, product["id"], target],
            )
        if cart_id is not None:
            conn.execute("UPDATE carts SET updated_at = now() WHERE id = %s", [cart_id])
    return get_cart(store, owner)


def merge_guest_cart(store: StoreId, guest_hash: str, customer_id: int) -> dict[str, Any]:
    """After sign-in, move a guest cart's items into the customer's cart (capped by stock and limits)."""
    owner = CartOwner(customer_id=customer_id)
    with store_connection(store) as conn, conn.transaction():
        guest_id = _find_cart(conn, CartOwner(guest_hash=guest_hash))
        if guest_id is not None:
            cart_id = _find_cart(conn, owner, create=True)
            for ln in _cart_lines(conn, guest_id):
                conn.execute(
                    "INSERT INTO cart_items (cart_id, product_id, quantity) VALUES (%(c)s, %(p)s, LEAST(%(q)s, %(max)s, GREATEST(%(stock)s, 1))) "
                    "ON CONFLICT (cart_id, product_id) DO UPDATE SET quantity = LEAST(cart_items.quantity + %(q)s, %(max)s, GREATEST(%(stock)s, 1))",
                    {"c": cart_id, "p": ln["product_id"], "q": ln["quantity"], "max": MAX_LINE_QTY, "stock": ln["stock_qty"]},
                )
            conn.execute("DELETE FROM carts WHERE id = %s", [guest_id])
    return get_cart(store, owner)


# ---- checkout --------------------------------------------------------------------------------
def validate_address(store: StoreId, address: dict[str, Any]) -> dict[str, Any]:
    """The destination country's rules (app/markets.py: states / union territories, ZIP or PIN, phone), then this store's
    own exclusions. Returns the normalised address (upper-case region, E.164 phone)."""
    from .markets import AddressError, get_market
    from .markets import validate_address as market_rules
    try:
        address = market_rules(get_market(address.get("country", "US")), address)
    except AddressError as e:
        raise CommerceError(422, "Please check the shipping address.", "validation_error", details=e.problems) from None
    if address["country"] == "US" and address["region"] in SHIPPING_EXCLUDED_REGIONS[store]:
        raise CommerceError(422, "Sorry, this store does not ship to that state.", "region_not_served",
                            details=[{"field": "shipping.region", "issue": "not served by this store"}])
    return address


def _existing_order(conn, customer_id: int, key: str) -> dict[str, Any] | None:
    return conn.execute(
        "SELECT order_number FROM orders WHERE customer_id = %s AND idempotency_key = %s", [customer_id, key]
    ).fetchone()


def place_order(store: StoreId, customer_id: int, idempotency_key: str, address: dict[str, Any], method: str,
                expected_total_cents: int, rates: Any = _US_RATES) -> tuple[dict[str, Any], bool]:
    """Returns (order, created). created=False means this key was already used and the original order is returned.
    `rates` are the destination's (shipping_zones.rates_for); None = no rates there → refused, nothing is created."""
    address = validate_address(store, address)
    if rates is _US_RATES:
        rates = repo.get_shipping_rates(store)
    if rates is None:
        raise CommerceError(409, SHIPPING_UNCONFIRMED, "shipping_not_configured",
                            details=[{"field": "shipping.country", "issue": "no delivery rates set for this destination"}])
    try:
        with store_connection(store) as conn, conn.transaction():
            if (prior := _existing_order(conn, customer_id, idempotency_key)) is not None:
                return repo.get_order_for_customer(store, prior["order_number"], customer_id), False
            cart = conn.execute("SELECT id FROM carts WHERE customer_id = %s AND status = 'open' FOR UPDATE", [customer_id]).fetchone()
            lines = _cart_lines(conn, cart["id"] if cart else None, lock_products=True)
            if not lines:
                # A concurrent duplicate submission may have just converted the cart: return its order.
                if (prior := _existing_order(conn, customer_id, idempotency_key)) is not None:
                    return repo.get_order_for_customer(store, prior["order_number"], customer_id), False
                raise CommerceError(409, "Your cart is empty.", "cart_empty")
            currency, lines = _priced(store, conn, lines, address["country"])
            view = _view(lines, rates, method, address["country"], currency)
            if not view["prices_available"]:
                raise CommerceError(409, view["price_problem"], "price_not_configured",
                                    details=[{"field": "cart", "issue": f"no approved {currency} price: {n}"} for n in view["unpriced_items"]])
            if view["shipping_cents"] is None:
                raise CommerceError(409, SHIPPING_UNCONFIRMED, "shipping_not_configured",
                                    details=[{"field": "shipping.country", "issue": "no delivery rates in this currency"}])
            if view["problems"]:
                raise CommerceError(409, "Some items are no longer available in the quantity requested.", "stock_changed",
                                    details=[{"field": "cart", "issue": p} for p in view["problems"]])
            if view["total_cents"] != expected_total_cents:
                raise CommerceError(409, "Prices or shipping changed since you reviewed your order. Please review it again.", "total_changed")

            number = ORDER_PREFIX[store] + str(conn.execute("SELECT nextval('order_number_seq') AS n").fetchone()["n"])
            order_id = conn.execute(
                "INSERT INTO orders (order_number, customer_id, status, idempotency_key, subtotal_cents, shipping_cents, total_cents, "
                "shipping_method, shipping_name, shipping_line1, shipping_line2, shipping_city, shipping_region, shipping_postal_code, shipping_country, shipping_phone, currency) "
                "VALUES (%s, %s, 'pending_payment', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                [number, customer_id, idempotency_key, view["subtotal_cents"], view["shipping_cents"], view["total_cents"], method,
                 address["full_name"], address["line1"], address.get("line2") or None, address["city"], address["region"],
                 address["postal_code"], address["country"], address.get("phone"), currency],
            ).fetchone()["id"]
            record_history(conn, order_id, None, "pending_payment", actor_role="customer", actor_id=customer_id, note="order placed")
            for ln in lines:
                conn.execute("INSERT INTO order_items (order_id, product_id, quantity, unit_price_cents) VALUES (%s, %s, %s, %s)",
                             [order_id, ln["product_id"], ln["quantity"], ln["price_cents"]])
                conn.execute("UPDATE products SET stock_qty = stock_qty - %s WHERE id = %s", [ln["quantity"], ln["product_id"]])
            conn.execute("UPDATE carts SET status = 'converted', updated_at = now() WHERE id = %s", [cart["id"]])
    except psycopg.errors.UniqueViolation:
        # Two submissions with the same key raced past the first check; the other one won.
        with store_connection(store) as conn:
            prior = _existing_order(conn, customer_id, idempotency_key)
        if prior is None:
            raise
        return repo.get_order_for_customer(store, prior["order_number"], customer_id), False
    log.info("order created store=%s", store.value)
    return repo.get_order_for_customer(store, number, customer_id), True


def _restock(conn, order_id: int) -> None:
    conn.execute(
        "UPDATE products p SET stock_qty = p.stock_qty + i.quantity FROM order_items i WHERE i.order_id = %s AND i.product_id = p.id",
        [order_id],
    )


def cancel_pending_order(store: StoreId, customer_id: int, order_number: str) -> dict[str, Any]:
    """A customer may cancel an order that has not been paid yet; its stock is released."""
    with store_connection(store) as conn, conn.transaction():
        order = _owned_order_for_update(conn, customer_id, order_number)
        if order["status"] == "cancelled":
            # A repeated request (double click, second tab) changes nothing and says so.
            raise CommerceError(409, "This order is already cancelled.", "already_cancelled")
        if order["status"] != "pending_payment":
            raise CommerceError(409, "Only unpaid orders can be cancelled here. Please contact support.", "invalid_state")
        if conn.execute("SELECT 1 FROM payments WHERE order_id = %s AND status = 'succeeded'", [order["id"]]).fetchone():
            raise CommerceError(409, "This order has already been paid.", "invalid_state")
        for p in conn.execute("SELECT id FROM payments WHERE order_id = %s AND status = 'pending'", [order["id"]]).fetchall():
            transition_payment(conn, p["id"], "pending", "cancelled")
        transition_order(conn, order["id"], "pending_payment", "cancelled", actor_role="customer", actor_id=customer_id)
        _restock(conn, order["id"])
    return repo.get_order_for_customer(store, order_number, customer_id)


def expire_unpaid_order(store: StoreId, order_number: str, provider: PaymentProvider, ttl_minutes: int) -> str:
    """Background expiry of ONE unpaid order (app.worker). Idempotent: returns what happened —
    'paid' (the provider says a payment succeeded: it is applied instead of cancelling), 'expired', or 'skipped'
    (no longer unpaid, not old enough, or locked by a request in progress)."""
    with store_connection(store) as conn:
        row = conn.execute("SELECT customer_id FROM orders WHERE order_number = %s AND status = 'pending_payment'",
                           [order_number]).fetchone()
        has_pending = row is not None and conn.execute(
            "SELECT 1 FROM payments p JOIN orders o ON o.id = p.order_id WHERE o.order_number = %s AND p.status = 'pending'",
            [order_number]).fetchone() is not None
    if row is None:
        return "skipped"
    if has_pending:
        # Never cancel an order the customer may have just paid for: ask the provider first (same path as the payment page).
        verify_payment(store, row["customer_id"], order_number, provider)
    with store_connection(store) as conn, conn.transaction():
        order = conn.execute(
            "SELECT id, status FROM orders WHERE order_number = %s AND status = 'pending_payment' "
            "AND placed_at < now() - make_interval(mins => %s) FOR UPDATE SKIP LOCKED", [order_number, ttl_minutes]).fetchone()
        if order is None:
            paid = conn.execute("SELECT status FROM orders WHERE order_number = %s", [order_number]).fetchone()
            return "paid" if paid and paid["status"] == "processing" else "skipped"
        if conn.execute("SELECT 1 FROM payments WHERE order_id = %s AND status = 'succeeded'", [order["id"]]).fetchone():
            return "skipped"
        for p in conn.execute("SELECT id FROM payments WHERE order_id = %s AND status = 'pending'", [order["id"]]).fetchall():
            transition_payment(conn, p["id"], "pending", "cancelled")
        transition_order(conn, order["id"], "pending_payment", "cancelled", note=f"unpaid after {ttl_minutes} minutes")
        _restock(conn, order["id"])
    log.info("unpaid order expired store=%s", store.value)
    return "expired"


def _owned_order_for_update(conn, customer_id: int, order_number: str) -> dict[str, Any]:
    order = conn.execute(
        "SELECT id, order_number, status, total_cents FROM orders WHERE order_number = %s AND customer_id = %s FOR UPDATE",
        [order_number.upper(), customer_id],
    ).fetchone()
    if order is None:
        raise CommerceError(404, "Order not found.", "not_found")
    return order


# ---- payments ---------------------------------------------------------------------------------
def _payment_view(p: dict[str, Any] | None, provider: PaymentProvider) -> dict[str, Any] | None:
    if p is None:
        return None
    return {"status": p["status"], "provider": p["provider"], "sandbox": provider.sandbox, "reference": p["provider_ref"],
            "amount": money(p["amount_cents"], (p.get("currency") or "USD").strip())}


def latest_payment(store: StoreId, customer_id: int, order_number: str, provider: PaymentProvider) -> dict[str, Any] | None:
    with store_connection(store) as conn:
        p = conn.execute(
            "SELECT p.* FROM payments p JOIN orders o ON o.id = p.order_id WHERE o.order_number = %s AND o.customer_id = %s "
            "ORDER BY p.id DESC LIMIT 1",
            [order_number.upper(), customer_id],
        ).fetchone()
    return _payment_view(p, provider)


def start_payment(store: StoreId, customer_id: int, order_number: str, provider: PaymentProvider) -> dict[str, Any]:
    """Create a provider payment for the order's server-side total (or return the one in progress)."""
    with store_connection(store) as conn:
        order = conn.execute(
            "SELECT id, status, total_cents, currency FROM orders WHERE order_number = %s AND customer_id = %s", [order_number.upper(), customer_id]
        ).fetchone()
        if order is None:
            raise CommerceError(404, "Order not found.", "not_found")
        if order["status"] != "pending_payment":
            raise CommerceError(409, "This order is not awaiting payment.", "invalid_state")
        active = conn.execute("SELECT * FROM payments WHERE order_id = %s AND status = 'pending'", [order["id"]]).fetchone()
        if active:
            return _payment_view(active, provider)
        currency = order["currency"].strip()   # the order's own currency (migration 0008), never converted
    created = provider.create_payment(store, order["total_cents"], currency)
    try:
        with store_connection(store) as conn:
            row = conn.execute(
                "INSERT INTO payments (order_id, provider, provider_ref, amount_cents, currency, status) VALUES (%s, %s, %s, %s, %s, 'pending') RETURNING *",
                [order["id"], provider.name, created.ref, order["total_cents"], currency],
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        # A concurrent request started a payment first; use that one.
        with store_connection(store) as conn:
            row = conn.execute("SELECT * FROM payments WHERE order_id = %s AND status IN ('pending', 'succeeded') ORDER BY id DESC LIMIT 1",
                               [order["id"]]).fetchone()
    return _payment_view(row, provider)


def pending_payment_ref_owned_by(store: StoreId, customer_id: int, ref: str) -> bool:
    """True if `ref` is this customer's payment attempt, still pending, for an order still awaiting payment."""
    with store_connection(store) as conn:
        return conn.execute(
            "SELECT 1 FROM payments p JOIN orders o ON o.id = p.order_id WHERE p.provider_ref = %s AND o.customer_id = %s "
            "AND p.status = 'pending' AND o.status = 'pending_payment'",
            [ref, customer_id],
        ).fetchone() is not None


def verify_payment(store: StoreId, customer_id: int, order_number: str, provider: PaymentProvider) -> dict[str, Any]:
    """Ask the PROVIDER for the payment's status and apply it. The request carries no status from the client."""
    with store_connection(store) as conn:
        order = conn.execute("SELECT id FROM orders WHERE order_number = %s AND customer_id = %s", [order_number.upper(), customer_id]).fetchone()
        if order is None:
            raise CommerceError(404, "Order not found.", "not_found")
        payment = conn.execute("SELECT * FROM payments WHERE order_id = %s ORDER BY id DESC LIMIT 1", [order["id"]]).fetchone()
    if payment is None:
        raise CommerceError(409, "No payment has been started for this order.", "no_payment")

    if payment["status"] == "pending":
        remote = provider.get_payment(store, payment["provider_ref"])
        try:
            with store_connection(store) as conn, conn.transaction():
                locked = _owned_order_for_update(conn, customer_id, order_number)
                current = conn.execute("SELECT status FROM payments WHERE id = %s FOR UPDATE", [payment["id"]]).fetchone()["status"]
                if current == "pending" and remote is not None and remote.status != "pending":
                    if remote.amount_cents != payment["amount_cents"] or remote.currency != payment["currency"] \
                            or payment["amount_cents"] != locked["total_cents"]:
                        log.warning("payment amount mismatch store=%s; not marking order paid", store.value)
                        transition_payment(conn, payment["id"], "pending", "failed")
                    elif remote.status == "succeeded":
                        transition_payment(conn, payment["id"], "pending", "succeeded")
                        if locked["status"] == "pending_payment":
                            transition_order(conn, locked["id"], "pending_payment", "processing", note="payment confirmed")
                        else:
                            # Paid after the order was cancelled: record it and flag for a refund instead of reviving the order.
                            log.warning("payment succeeded for non-pending order store=%s status=%s; needs refund", store.value, locked["status"])
                    else:
                        transition_payment(conn, payment["id"], "pending", remote.status)
        except (InvalidTransition, ConcurrentChange):
            log.info("payment verification raced with another update store=%s", store.value)

    return {"order": repo.get_order_for_customer(store, order_number, customer_id),
            "payment": latest_payment(store, customer_id, order_number, provider)}

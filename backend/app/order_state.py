"""Order and payment state machines.

Every status change goes through `transition_order` / `transition_payment`, which
refuse transitions that are not listed here and use a compare-and-set UPDATE so two
concurrent requests cannot both move the same order.

    pending_payment ──paid──▶ processing ──▶ shipped ──▶ out_for_delivery ──▶ delivered ──▶ returned
          │                       │             └──────────────────────────────▶ delivered
          └──cancel──▶ cancelled ◀┘             └──▶ returned
"""

from __future__ import annotations

ORDER_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending_payment": frozenset({"processing", "cancelled"}),
    "processing": frozenset({"shipped", "cancelled"}),
    "shipped": frozenset({"out_for_delivery", "delivered", "returned"}),
    "out_for_delivery": frozenset({"delivered"}),
    "delivered": frozenset({"returned"}),
    "cancelled": frozenset(),
    "returned": frozenset(),
}

# A payment attempt is final once it leaves "pending"; retries create a new attempt.
PAYMENT_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"succeeded", "failed", "cancelled"}),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


class InvalidTransition(Exception):
    pass


class ConcurrentChange(Exception):
    """The row was no longer in the expected state when we tried to update it."""


def can_transition(table: dict[str, frozenset[str]], current: str, target: str) -> bool:
    return target in table.get(current, frozenset())


ACTOR_ROLES = frozenset({"customer", "agent", "system"})


def record_history(conn, order_id: int, from_status: str | None, to_status: str, *, actor_role: str,
                   actor_id: int | None = None, note: str | None = None, carrier: str | None = None,
                   tracking_number: str | None = None) -> None:
    """Append one row to order_status_history (migration 0005), in the caller's transaction."""
    if actor_role not in ACTOR_ROLES or (actor_role == "system") != (actor_id is None):
        raise ValueError("actor_role/actor_id mismatch")
    conn.execute(
        "INSERT INTO order_status_history (order_id, from_status, to_status, actor_role, actor_customer_id, note, carrier, tracking_number) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        [order_id, from_status, to_status, actor_role, actor_id, note, carrier, tracking_number],
    )


def transition_order(conn, order_id: int, current: str, target: str, *, actor_role: str = "system",
                     actor_id: int | None = None, note: str | None = None, carrier: str | None = None,
                     tracking_number: str | None = None) -> None:
    """Validated compare-and-set status change, recorded in order_status_history in the same transaction
    (so a status change can never exist without its history row, or the reverse)."""
    if not can_transition(ORDER_TRANSITIONS, current, target):
        raise InvalidTransition(f"order {current} -> {target}")
    cur = conn.execute("UPDATE orders SET status = %s, updated_at = now() WHERE id = %s AND status = %s", [target, order_id, current])
    if cur.rowcount != 1:
        raise ConcurrentChange("order")
    record_history(conn, order_id, current, target, actor_role=actor_role, actor_id=actor_id, note=note,
                   carrier=carrier, tracking_number=tracking_number)


def transition_payment(conn, payment_id: int, current: str, target: str) -> None:
    if not can_transition(PAYMENT_TRANSITIONS, current, target):
        raise InvalidTransition(f"payment {current} -> {target}")
    cur = conn.execute("UPDATE payments SET status = %s, updated_at = now() WHERE id = %s AND status = %s", [target, payment_id, current])
    if cur.rowcount != 1:
        raise ConcurrentChange("payment")

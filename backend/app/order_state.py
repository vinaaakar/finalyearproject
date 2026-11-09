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


def transition_order(conn, order_id: int, current: str, target: str) -> None:
    if not can_transition(ORDER_TRANSITIONS, current, target):
        raise InvalidTransition(f"order {current} -> {target}")
    cur = conn.execute("UPDATE orders SET status = %s, updated_at = now() WHERE id = %s AND status = %s", [target, order_id, current])
    if cur.rowcount != 1:
        raise ConcurrentChange("order")


def transition_payment(conn, payment_id: int, current: str, target: str) -> None:
    if not can_transition(PAYMENT_TRANSITIONS, current, target):
        raise InvalidTransition(f"payment {current} -> {target}")
    cur = conn.execute("UPDATE payments SET status = %s, updated_at = now() WHERE id = %s AND status = %s", [target, payment_id, current])
    if cur.rowcount != 1:
        raise ConcurrentChange("payment")

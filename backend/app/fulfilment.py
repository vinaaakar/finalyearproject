"""Staff order fulfilment (Phase F).

Every action:
- runs in ONE transaction with the order row locked (SELECT … FOR UPDATE);
- is validated by the order state machine (`order_state.ORDER_TRANSITIONS`) — anything else is refused with 409;
- checks the status the staff member was looking at (`expected_status`), so a stale screen can't act twice;
- writes an `order_status_history` row naming the staff account (same transaction as the change).

Callers (routers/staff.py) must have verified an agent role FOR THIS STORE (`deps.require_agent`, whose token is bound to
one store). Customers have no route to any of this, and customer-facing endpoints accept no fulfilment fields.

Not done here, deliberately:
- cancelling a PAID order (it would need a refund, and refunds/payment changes are out of scope);
- changing stock when an order is returned (whether returned goods are resaleable is a business decision);
- carrier tracking-URL templates (which carriers the stores use is a business decision, docs/business-information.md B20).
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from . import repositories as repo
from .commerce import CommerceError
from .order_state import ORDER_TRANSITIONS, ConcurrentChange, InvalidTransition, can_transition, record_history, transition_order
from .repositories import store_connection
from .stores import StoreId

log = logging.getLogger("app.fulfilment")

# action → target status
ACTIONS = {"ship": "shipped", "out_for_delivery": "out_for_delivery", "deliver": "delivered", "return": "returned"}


def _locked(conn, order_number: str) -> dict[str, Any]:
    row = conn.execute("SELECT id, order_number, status FROM orders WHERE order_number = %s FOR UPDATE", [order_number.upper()]).fetchone()
    if row is None:
        raise CommerceError(404, "Order not found.", "not_found")
    return row


def apply_action(store: StoreId, agent_id: int, order_number: str, action: str, *, expected_status: str,
                 carrier: str | None = None, tracking_number: str | None = None, tracking_url: str | None = None,
                 estimated_delivery: date | None = None, note: str | None = None) -> dict[str, Any]:
    target = ACTIONS.get(action)
    if target is None:
        raise CommerceError(400, "Unknown action.", "invalid_action")
    with store_connection(store) as conn, conn.transaction():
        order = _locked(conn, order_number)
        current = order["status"]
        if current != expected_status:
            raise CommerceError(409, f"This order is now “{current.replace('_', ' ')}”. Reload it before changing it.", "stale_status",
                                details=[{"field": "expected_status", "issue": current}])
        if not can_transition(ORDER_TRANSITIONS, current, target):
            raise CommerceError(409, f"An order that is “{current.replace('_', ' ')}” can’t be marked “{target.replace('_', ' ')}”.",
                                "invalid_transition")
        if target == "shipped":
            if not carrier or not tracking_number:
                raise CommerceError(422, "Carrier and tracking number are required to ship an order.", "validation_error")
            conn.execute(
                "UPDATE orders SET carrier = %s, tracking_number = %s, tracking_url = %s, "
                "estimated_delivery = coalesce(%s, estimated_delivery), shipped_at = now() WHERE id = %s",
                [carrier, tracking_number, tracking_url, estimated_delivery, order["id"]],
            )
        elif target == "delivered":
            conn.execute("UPDATE orders SET delivered_at = now() WHERE id = %s", [order["id"]])
        if target == "shipped":
            # The customer's "your order has shipped" e-mail, queued in the same transaction (sent by app.worker).
            conn.execute("INSERT INTO outbox (kind, dedupe_key, payload) VALUES ('email.order_shipped', %s, %s::jsonb) "
                         "ON CONFLICT (dedupe_key) DO NOTHING",
                         [f"order_shipped:{order['order_number']}", json.dumps({"order_number": order["order_number"]})])
        try:
            transition_order(conn, order["id"], current, target, actor_role="agent", actor_id=agent_id, note=note,
                             carrier=carrier if target == "shipped" else None,
                             tracking_number=tracking_number if target == "shipped" else None)
        except (InvalidTransition, ConcurrentChange) as e:   # defensive: the row is locked, so this should not happen
            raise CommerceError(409, "The order changed while you were updating it. Reload it and try again.", "concurrent_change") from e
    log.info("fulfilment store=%s action=%s %s->%s", store.value, action, current, target)
    return repo.get_staff_order(store, order_number)


def update_tracking(store: StoreId, agent_id: int, order_number: str, *, carrier: str, tracking_number: str,
                    tracking_url: str | None, note: str | None) -> dict[str, Any]:
    """Correct the carrier/tracking of an order that is already on its way (no status change; recorded in history)."""
    with store_connection(store) as conn, conn.transaction():
        order = _locked(conn, order_number)
        if order["status"] not in ("shipped", "out_for_delivery"):
            raise CommerceError(409, "Tracking can only be changed while an order is on its way.", "invalid_transition")
        conn.execute("UPDATE orders SET carrier = %s, tracking_number = %s, tracking_url = %s, updated_at = now() WHERE id = %s",
                     [carrier, tracking_number, tracking_url, order["id"]])
        record_history(conn, order["id"], order["status"], order["status"], actor_role="agent", actor_id=agent_id,
                       note=note or "tracking updated", carrier=carrier, tracking_number=tracking_number)
    return repo.get_staff_order(store, order_number)

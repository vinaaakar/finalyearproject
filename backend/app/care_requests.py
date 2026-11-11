"""Customer-care requests: complaints, return requests, SIMULATED refund requests and human-help (escalation) requests.

One service used by the customer API, the staff API and the assistants (Scout / Maple), so every path applies the same
rules:
- Store isolation: each store has its own database; references carry the store prefix (SA-RET-00001, BB-CMP-00002).
- Customer scope: a customer can only create, see, reply to or withdraw their OWN requests, about their OWN orders. Any
  other reference / order number gets the same 404 as one that doesn't exist (no existence leak).
- Staff scope: callers must have verified an agent of THIS store (deps.require_agent). Only staff change statuses; every
  change is validated against the transition table below, checks the status the staff member was looking at
  (`expected_status`), and is written to care_request_events in the same transaction.
- Eligibility comes only from existing data: returns from the order's delivery date and the store's own return-policy
  window; refunds from a recorded successful (sandbox) payment. Nothing is invented.
- Refunds are SIMULATED: no payment provider is called, no money moves; "simulated_completed" is a staff record only.
- Submitting a return never changes the order or its fulfilment status (staff still use the existing order actions).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from typing import Any

import psycopg

from . import repositories as repo
from .commerce import CommerceError
from .repositories import store_connection
from .stores import ORDER_PREFIX, StoreId

log = logging.getLogger("app.care")

KINDS = ("complaint", "return", "refund", "escalation")
CODE = {"complaint": "CMP", "return": "RET", "refund": "RFD", "escalation": "ESC"}
KIND_OF_CODE = {v: k for k, v in CODE.items()}
CATEGORIES: dict[str, tuple[str, ...]] = {
    "complaint": ("damaged", "wrong_item", "missing_item", "quality", "delivery", "other"),
    "return": ("damaged", "wrong_item", "not_as_described", "no_longer_needed", "other"),
    "refund": ("damaged", "wrong_item", "missing_item", "not_delivered", "charged_incorrectly", "returned_item", "other"),
    "escalation": ("order_problem", "payment_problem", "delivery_problem", "account_problem", "follow_up", "other"),
}
INITIAL = {"complaint": "open", "return": "requested", "refund": "requested", "escalation": "open"}
# Staff-only transitions. Customers can only withdraw (from the initial status) and reply.
TRANSITIONS: dict[str, dict[str, frozenset[str]]] = {
    "complaint": {
        "open": frozenset({"under_review", "rejected", "closed"}),
        "under_review": frozenset({"awaiting_customer", "resolved", "rejected", "closed"}),
        "awaiting_customer": frozenset({"under_review", "resolved", "closed"}),
    },
    "return": {
        "requested": frozenset({"under_review", "rejected"}),
        "under_review": frozenset({"approved", "rejected"}),
        "approved": frozenset({"received", "closed"}),
        "received": frozenset({"inspected"}),
        "inspected": frozenset({"completed"}),
    },
    "refund": {
        "requested": frozenset({"under_review", "rejected"}),
        "under_review": frozenset({"approved", "rejected"}),
        "approved": frozenset({"simulated_completed"}),
    },
    "escalation": {
        "open": frozenset({"assigned", "in_progress", "resolved", "closed"}),
        "assigned": frozenset({"in_progress", "resolved", "closed"}),
        "in_progress": frozenset({"awaiting_customer", "resolved", "closed"}),
        "awaiting_customer": frozenset({"in_progress", "resolved", "closed"}),
    },
}
TERMINAL = frozenset({"rejected", "completed", "simulated_completed", "resolved", "closed", "withdrawn"})
NEEDS_REASON = frozenset({"rejected", "closed"})        # the customer is told why (customer-visible message required)
REPLY_RETURNS_TO = {"complaint": "under_review", "escalation": "in_progress"}
STATUS_LABELS = {
    "open": "Open", "requested": "Requested", "under_review": "Under review", "awaiting_customer": "Waiting for your reply",
    "assigned": "Assigned to staff", "in_progress": "In progress", "approved": "Approved", "rejected": "Rejected",
    "received": "Item received", "inspected": "Item inspected", "completed": "Completed",
    "simulated_completed": "Refund completed (simulated — no money moved)", "resolved": "Resolved", "closed": "Closed",
    "withdrawn": "Withdrawn",
}
SIMULATED_REFUND_NOTICE = ("Refunds in this academic demonstration are simulated: no payment provider is contacted and "
                           "no real money is transferred.")
_REF_RE = re.compile(r"^(SA|BB)-(CMP|RET|RFD|ESC)-\d{5,}$")


def _err(_status: int, _text: str, _code: str, /, **detail) -> CommerceError:
    """detail: field → issue (any field name, including "message")."""
    return CommerceError(_status, _text, _code, details=[{"field": k, "issue": str(v)} for k, v in detail.items()] or None)


def _clean(text: str | None, limit: int = 1000) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()[:limit + 1]


def _check_text(text: str, field: str) -> str:
    from .assistant.intent import sensitive_kind
    text = _clean(text)
    if not text:
        raise _err(422, "Please describe the problem in a few words.", "validation_error", **{field: "required"})
    if len(text) > 1000:
        raise _err(422, "Please keep the description under 1,000 characters.", "validation_error", **{field: "too long"})
    if sensitive_kind(text):
        # Never stored: card numbers, CVV, UPI PIN, passwords, one-time codes, bank credentials.
        raise _err(422, "Please don't include card numbers, CVV, UPI PIN, passwords or other secret codes. They are never "
                        "needed for a request.", "sensitive_data", **{field: "contains sensitive data"})
    return text


def return_window_days(store: StoreId) -> int | None:
    """Days from the store's OWN returns policy ("… within 60 days …"); None if the policy states none."""
    text = repo.get_policies(store, "en").get("returns", {}).get("details", "")
    m = re.search(r"within (\d{1,3}) days", text)
    return int(m.group(1)) if m else None


# ---- reads -------------------------------------------------------------------------------------------------------------
def _order(conn, customer_id: int, order_number: str, lock: bool = False) -> dict[str, Any] | None:
    return conn.execute(
        "SELECT id, order_number, status, delivered_at, estimated_delivery, total_cents, currency FROM orders "
        "WHERE order_number = %s AND customer_id = %s" + (" FOR UPDATE" if lock else ""),
        [(order_number or "").strip().upper(), customer_id]).fetchone()


def _items(conn, order_id: int) -> list[dict[str, Any]]:
    return conn.execute("SELECT i.id, p.name, p.slug, i.quantity FROM order_items i JOIN products p ON p.id = i.product_id "
                        "WHERE i.order_id = %s ORDER BY i.id", [order_id]).fetchall()


def _open_requests(conn, order_id: int) -> list[dict[str, Any]]:
    return conn.execute("SELECT reference, kind, order_item_id FROM care_requests WHERE order_id = %s AND status <> ALL(%s)",
                        [order_id, list(TERMINAL)]).fetchall()


def eligibility(store: StoreId, conn, kind: str, order: dict[str, Any] | None) -> dict[str, Any]:
    """{"eligible": bool, "reason": code | None, "until": iso date | None} — from recorded data only."""
    if kind in ("complaint", "escalation"):
        return {"eligible": True, "reason": None, "until": None}
    if order is None:
        return {"eligible": False, "reason": "order_required", "until": None}
    if kind == "return":
        if order["status"] != "delivered":
            return {"eligible": False, "reason": "not_delivered", "until": None, "status": order["status"]}
        days = return_window_days(store)
        delivered = order["delivered_at"].date() if order["delivered_at"] else order["estimated_delivery"]
        if days is None or delivered is None:
            return {"eligible": False, "reason": "window_unknown", "until": None}
        until = delivered + timedelta(days=days)
        if date.today() > until:
            return {"eligible": False, "reason": "window_passed", "until": until.isoformat(), "days": days}
        return {"eligible": True, "reason": None, "until": until.isoformat(), "days": days}
    # refund: only for an order with a recorded successful (sandbox) payment
    paid = conn.execute("SELECT 1 FROM payments WHERE order_id = %s AND status = 'succeeded' LIMIT 1", [order["id"]]).fetchone()
    if not paid:
        return {"eligible": False, "reason": "not_paid", "until": None}
    return {"eligible": True, "reason": None, "until": None}


def options(store: StoreId, customer_id: int, kind: str, order_number: str | None = None) -> dict[str, Any]:
    """What the customer can choose for a new request: categories, and either their orders (with eligibility) or one
    order's items (with any request already open for each)."""
    if kind not in KINDS:
        raise _err(422, "Unknown request type.", "validation_error", kind="unknown")
    with store_connection(store) as conn:
        if order_number:
            order = _order(conn, customer_id, order_number)
            if order is None:
                raise _err(404, f"Order {order_number.upper()} wasn't found on your account.", "not_found")
            open_ = _open_requests(conn, order["id"])
            items = [{"id": i["id"], "name": i["name"], "quantity": i["quantity"],
                      "open_request": next((o["reference"] for o in open_ if o["kind"] == kind and o["order_item_id"] == i["id"]), None)}
                     for i in _items(conn, order["id"])]
            return {"kind": kind, "categories": list(CATEGORIES[kind]), "simulated": kind == "refund",
                    "order": {"order_number": order["order_number"], "status": order["status"], **eligibility(store, conn, kind, order)},
                    "items": items,
                    "open_for_order": next((o["reference"] for o in open_ if o["kind"] == kind and o["order_item_id"] is None), None)}
        orders = conn.execute(
            "SELECT id, order_number, status, delivered_at, estimated_delivery, total_cents, currency, placed_at FROM orders "
            "WHERE customer_id = %s ORDER BY placed_at DESC LIMIT 20", [customer_id]).fetchall()
        return {"kind": kind, "categories": list(CATEGORIES[kind]), "simulated": kind == "refund",
                "orders": [{"order_number": o["order_number"], "status": o["status"], **eligibility(store, conn, kind, o)} for o in orders]}


# ---- create -------------------------------------------------------------------------------------------------------------
def create(store: StoreId, customer_id: int, *, kind: str, category: str, description: str, order_number: str | None = None,
           item_id: int | None = None, idempotency_key: str | None = None) -> tuple[dict[str, Any], bool]:
    """Register a request for the signed-in customer. Returns (customer view, created). created=False: the same
    idempotency key was used before, and the original request is returned."""
    if kind not in KINDS:
        raise _err(422, "Unknown request type.", "validation_error", kind="unknown")
    if category not in CATEGORIES[kind]:
        raise _err(422, "Please choose one of the listed reasons.", "validation_error", category="not one of the options")
    description = _check_text(description, "description")
    if kind in ("return", "refund") and not order_number:
        raise _err(422, "Please choose the order this is about.", "validation_error", order_number="required")
    if item_id is not None and not order_number:
        raise _err(422, "Please choose the order first.", "validation_error", order_number="required")
    try:
        with store_connection(store) as conn, conn.transaction():
            if idempotency_key:
                prior = conn.execute("SELECT id FROM care_requests WHERE customer_id = %s AND idempotency_key = %s",
                                     [customer_id, idempotency_key]).fetchone()
                if prior:
                    return _customer_view(conn, prior["id"]), False
            order = None
            if order_number:
                order = _order(conn, customer_id, order_number, lock=True)
                if order is None:
                    raise _err(404, f"Order {order_number.upper()} wasn't found on your account.", "not_found")
            items = _items(conn, order["id"]) if order else []
            if item_id is not None and item_id not in {i["id"] for i in items}:
                raise _err(422, "That item isn't part of this order.", "validation_error", item_id="not in this order")
            if kind == "return" and item_id is None:
                if len(items) != 1:
                    raise _err(422, "Please choose the item you want to return.", "validation_error", item_id="required")
                item_id = items[0]["id"]
            elig = eligibility(store, conn, kind, order)
            if not elig["eligible"]:
                raise CommerceError(409, _ineligible_message(kind, elig, order), "not_eligible",
                                    details=[{"field": "order_number", "issue": elig["reason"]}])
            n = conn.execute("SELECT nextval('care_request_seq') AS n").fetchone()["n"]
            reference = f"{ORDER_PREFIX[store]}{CODE[kind]}-{n:05d}"
            rid = conn.execute(
                "INSERT INTO care_requests (reference, kind, customer_id, order_id, order_item_id, category, description, status, "
                "idempotency_key) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                [reference, kind, customer_id, order["id"] if order else None, item_id, category, description, INITIAL[kind],
                 idempotency_key]).fetchone()["id"]
            _event(conn, rid, "created", None, INITIAL[kind], "customer", "customer", customer_id, None)
            view = _customer_view(conn, rid)
    except psycopg.errors.UniqueViolation as e:
        # Another open request of this kind exists for the same order item (or a racing duplicate submission).
        with store_connection(store) as conn:
            if idempotency_key:
                prior = conn.execute("SELECT id FROM care_requests WHERE customer_id = %s AND idempotency_key = %s",
                                     [customer_id, idempotency_key]).fetchone()
                if prior:
                    return _customer_view(conn, prior["id"]), False
            order = _order(conn, customer_id, order_number) if order_number else None
            existing = conn.execute(
                "SELECT reference FROM care_requests WHERE kind = %s AND order_id = %s AND coalesce(order_item_id, 0) = %s "
                "AND status <> ALL(%s)", [kind, order["id"] if order else None, item_id or 0, list(TERMINAL)]).fetchone()
        if existing:
            raise CommerceError(409, f"You already have an open request for this: {existing['reference']}.", "duplicate_request",
                                details=[{"field": "reference", "issue": existing["reference"]}]) from e
        raise
    log.info("care request created store=%s kind=%s", store.value, kind)
    return view, True


def _ineligible_message(kind: str, elig: dict[str, Any], order: dict[str, Any] | None) -> str:
    number = order["order_number"] if order else ""
    reason = elig["reason"]
    if reason == "not_delivered":
        return (f"Order {number} hasn't been delivered yet ({order['status'].replace('_', ' ')}), so a return can't be requested. "
                "You can report a problem or ask for human help instead.")
    if reason == "window_passed":
        return (f"The return window for order {number} ended on {elig['until']} ({elig['days']} days from delivery, as the "
                "store's returns policy states). You can report a problem or ask for human help instead.")
    if reason == "window_unknown":
        return "The store's returns policy doesn't state a return window for this order, so staff need to look at it: please ask for human help."
    if reason == "not_paid":
        return f"There's no completed payment recorded for order {number}, so there's nothing to refund."
    return "Please choose the order this is about."


# ---- customer side ----------------------------------------------------------------------------------------------------------
def _event(conn, request_id: int, event: str, from_status: str | None, to_status: str | None, visibility: str,
           actor_role: str, actor_id: int | None, body: str | None) -> int:
    eid = conn.execute(
        "INSERT INTO care_request_events (request_id, event, from_status, to_status, visibility, body, actor_role, actor_customer_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        [request_id, event, from_status, to_status, visibility, body, actor_role, actor_id]).fetchone()["id"]
    conn.execute("UPDATE care_requests SET updated_at = now() WHERE id = %s", [request_id])
    return eid


def _row(conn, *, rid: int | None = None, reference: str | None = None, customer_id: int | None = None, lock: bool = False):
    sql = ("SELECT r.*, o.order_number, o.status AS order_status, i.quantity AS item_quantity, p.name AS item_name "
           "FROM care_requests r LEFT JOIN orders o ON o.id = r.order_id LEFT JOIN order_items i ON i.id = r.order_item_id "
           "LEFT JOIN products p ON p.id = i.product_id WHERE ")
    args: list[Any] = []
    if rid is not None:
        sql += "r.id = %s"; args.append(rid)
    else:
        sql += "r.reference = %s"; args.append((reference or "").strip().upper())
    if customer_id is not None:
        sql += " AND r.customer_id = %s"; args.append(customer_id)
    if lock:
        sql += " FOR UPDATE OF r"
    return conn.execute(sql, args).fetchone()


def _iso(v):
    return v.isoformat() if v is not None else None


def _base_view(r: dict[str, Any]) -> dict[str, Any]:
    return {"reference": r["reference"], "kind": r["kind"], "category": r["category"], "description": r["description"],
            "status": r["status"], "status_label": STATUS_LABELS[r["status"]], "order_number": r["order_number"],
            "item": {"id": r["order_item_id"], "name": r["item_name"], "quantity": r["item_quantity"]} if r["order_item_id"] else None,
            "created_at": _iso(r["created_at"]), "updated_at": _iso(r["updated_at"]), "resolved_at": _iso(r["resolved_at"]),
            "open": r["status"] not in TERMINAL, "simulated": r["kind"] == "refund",
            "simulated_notice": SIMULATED_REFUND_NOTICE if r["kind"] == "refund" else None}


def _customer_view(conn, rid: int, row=None) -> dict[str, Any]:
    r = row or _row(conn, rid=rid)
    events = conn.execute("SELECT event, to_status, body, actor_role, created_at FROM care_request_events "
                          "WHERE request_id = %s AND visibility = 'customer' ORDER BY created_at, id", [r["id"]]).fetchall()
    return {**_base_view(r), "assigned": r["assigned_to"] is not None,
            "can_withdraw": r["status"] == INITIAL[r["kind"]],
            "can_reply": r["status"] not in TERMINAL,
            # Customer-visible history only: internal staff notes and the staff member's identity are never included.
            "updates": [{"event": e["event"], "status": e["to_status"], "status_label": STATUS_LABELS.get(e["to_status"] or "", None),
                         "message": e["body"], "by": {"customer": "you", "agent": "staff", "system": "system"}[e["actor_role"]],
                         "at": _iso(e["created_at"])} for e in events]}


def list_for_customer(store: StoreId, customer_id: int, kind: str | None = None) -> list[dict[str, Any]]:
    with store_connection(store) as conn:
        rows = conn.execute("SELECT r.id FROM care_requests r WHERE r.customer_id = %s AND (%s::text IS NULL OR r.kind = %s) "
                            "ORDER BY r.created_at DESC LIMIT 50", [customer_id, kind, kind]).fetchall()
        return [{k: v for k, v in _customer_view(conn, r["id"]).items() if k != "updates"} for r in rows]


def get_for_customer(store: StoreId, customer_id: int, reference: str) -> dict[str, Any]:
    if not _REF_RE.match((reference or "").upper()):
        raise _err(404, "Request not found.", "not_found")
    with store_connection(store) as conn:
        r = _row(conn, reference=reference, customer_id=customer_id)
        if r is None:
            raise _err(404, "Request not found.", "not_found")
        return _customer_view(conn, r["id"], r)


def customer_reply(store: StoreId, customer_id: int, reference: str, message: str) -> dict[str, Any]:
    message = _check_text(message, "message")
    with store_connection(store) as conn, conn.transaction():
        r = _row(conn, reference=reference, customer_id=customer_id, lock=True)
        if r is None:
            raise _err(404, "Request not found.", "not_found")
        if r["status"] in TERMINAL:
            raise _err(409, "This request is closed. Please start a new one if you still need help.", "invalid_state")
        _event(conn, r["id"], "customer_reply", None, None, "customer", "customer", customer_id, message)
        back = REPLY_RETURNS_TO.get(r["kind"])
        if r["status"] == "awaiting_customer" and back:
            _set_status(conn, r, back, "customer", customer_id)
        return _customer_view(conn, r["id"])


def withdraw(store: StoreId, customer_id: int, reference: str) -> dict[str, Any]:
    with store_connection(store) as conn, conn.transaction():
        r = _row(conn, reference=reference, customer_id=customer_id, lock=True)
        if r is None:
            raise _err(404, "Request not found.", "not_found")
        if r["status"] != INITIAL[r["kind"]]:
            raise _err(409, "Staff have already started on this request, so it can't be withdrawn. You can send them a message instead.",
                       "invalid_state")
        _set_status(conn, r, "withdrawn", "customer", customer_id)
        return _customer_view(conn, r["id"])


def _set_status(conn, r: dict[str, Any], target: str, actor_role: str, actor_id: int | None, body: str | None = None) -> int:
    updated = conn.execute(
        "UPDATE care_requests SET status = %s, updated_at = now(), resolved_at = CASE WHEN %s THEN now() ELSE resolved_at END "
        "WHERE id = %s AND status = %s", [target, target in TERMINAL, r["id"], r["status"]]).rowcount
    if updated != 1:
        raise _err(409, "This request changed while you were updating it. Reload it and try again.", "concurrent_change")
    eid = _event(conn, r["id"], "status", r["status"], target, "customer", actor_role, actor_id, body)
    r["status"] = target
    return eid


# ---- staff side -------------------------------------------------------------------------------------------------------------
def _queue_email(conn, r: dict[str, Any], event_id: int) -> None:
    """Tell the customer something changed (sent by app.worker through the existing outbox; dev: .run/outbox/)."""
    conn.execute("INSERT INTO outbox (kind, dedupe_key, payload) VALUES ('email.care_update', %s, %s::jsonb) "
                 "ON CONFLICT (dedupe_key) DO NOTHING", [f"care_event:{event_id}", json.dumps({"reference": r["reference"]})])


def staff_list(store: StoreId, *, kinds: list[str] | None = None, statuses: list[str] | None = None, query: str | None = None,
               date_from: date | None = None, date_to: date | None = None, limit: int = 25, offset: int = 0) -> tuple[list[dict], int]:
    where, args = ["TRUE"], []
    if kinds:
        where.append("r.kind = ANY(%s)"); args.append(kinds)
    if statuses:
        where.append("r.status = ANY(%s)"); args.append(statuses)
    if query:
        where.append("(r.reference = %s OR o.order_number = %s)"); args += [query.strip().upper()] * 2
    if date_from:
        where.append("r.created_at >= %s"); args.append(date_from)
    if date_to:
        where.append("r.created_at < %s"); args.append(date_to + timedelta(days=1))
    w = " AND ".join(where)
    with store_connection(store) as conn:
        total = conn.execute(f"SELECT count(*) AS n FROM care_requests r LEFT JOIN orders o ON o.id = r.order_id WHERE {w}", args).fetchone()["n"]
        rows = conn.execute(
            "SELECT r.*, o.order_number, o.status AS order_status, i.quantity AS item_quantity, p.name AS item_name, "
            "c.full_name AS customer_name, a.full_name AS assigned_name FROM care_requests r "
            "LEFT JOIN orders o ON o.id = r.order_id LEFT JOIN order_items i ON i.id = r.order_item_id "
            "LEFT JOIN products p ON p.id = i.product_id JOIN customers c ON c.id = r.customer_id "
            f"LEFT JOIN customers a ON a.id = r.assigned_to WHERE {w} ORDER BY (r.status = ANY(%s)), r.created_at DESC "
            "LIMIT %s OFFSET %s", [*args, list(TERMINAL), limit, offset]).fetchall()
    return [{**_base_view(r), "customer_name": r["customer_name"], "assigned_to": r["assigned_name"],
             "actions": sorted(TRANSITIONS[r["kind"]].get(r["status"], ()))} for r in rows], total


def staff_get(store: StoreId, reference: str) -> dict[str, Any]:
    if not _REF_RE.match((reference or "").upper()):
        raise _err(404, "Request not found.", "not_found")
    with store_connection(store) as conn:
        r = _row(conn, reference=reference)
        if r is None:
            raise _err(404, "Request not found.", "not_found")
        return _staff_view(conn, store, r)


def _staff_view(conn, store: StoreId, r: dict[str, Any]) -> dict[str, Any]:
    c = conn.execute("SELECT full_name, email FROM customers WHERE id = %s", [r["customer_id"]]).fetchone()
    a = conn.execute("SELECT id, full_name FROM customers WHERE id = %s", [r["assigned_to"]]).fetchone() if r["assigned_to"] else None
    order = None
    if r["order_id"]:
        o = conn.execute("SELECT order_number, status, total_cents, currency, placed_at, delivered_at, estimated_delivery "
                         "FROM orders WHERE id = %s", [r["order_id"]]).fetchone()
        from .commerce import money
        paid = conn.execute("SELECT status, amount_cents, currency FROM payments WHERE order_id = %s ORDER BY id DESC LIMIT 1",
                            [r["order_id"]]).fetchone()
        order = {"order_number": o["order_number"], "status": o["status"], "total": money(o["total_cents"], o["currency"].strip()),
                 "placed_at": _iso(o["placed_at"]), "delivered_at": _iso(o["delivered_at"]),
                 "estimated_delivery": _iso(o["estimated_delivery"]),
                 "payment": {"status": paid["status"], "amount": money(paid["amount_cents"], paid["currency"].strip())} if paid else None,
                 "items": [{"id": i["id"], "name": i["name"], "quantity": i["quantity"]} for i in _items(conn, r["order_id"])],
                 "return_eligibility": eligibility(store, conn, "return", o | {"id": r["order_id"]}) if r["kind"] == "return" else None}
    events = conn.execute(
        "SELECT e.event, e.from_status, e.to_status, e.visibility, e.body, e.actor_role, e.created_at, c.full_name AS actor_name "
        "FROM care_request_events e LEFT JOIN customers c ON c.id = e.actor_customer_id WHERE e.request_id = %s "
        "ORDER BY e.created_at, e.id", [r["id"]]).fetchall()
    return {**_base_view(r), "customer": {"name": c["full_name"], "email": c["email"]}, "order": order,
            "assigned_to": {"id": a["id"], "name": a["full_name"]} if a else None,
            "actions": sorted(TRANSITIONS[r["kind"]].get(r["status"], ())), "reason_required_for": sorted(NEEDS_REASON),
            "history": [{"event": e["event"], "from_status": e["from_status"], "to_status": e["to_status"],
                         "visibility": e["visibility"], "body": e["body"], "by": e["actor_name"] if e["actor_role"] != "system" else "system",
                         "role": e["actor_role"], "at": _iso(e["created_at"])} for e in events]}


def staff_agents(store: StoreId) -> list[dict[str, Any]]:
    with store_connection(store) as conn:
        return [dict(r) for r in conn.execute("SELECT id, full_name AS name FROM customers WHERE role = 'agent' ORDER BY full_name").fetchall()]


def _locked_for_staff(conn, reference: str, expected_status: str | None) -> dict[str, Any]:
    if not _REF_RE.match((reference or "").upper()):
        raise _err(404, "Request not found.", "not_found")
    r = _row(conn, reference=reference, lock=True)
    if r is None:
        raise _err(404, "Request not found.", "not_found")
    if expected_status is not None and r["status"] != expected_status:
        raise _err(409, f"This request is now “{STATUS_LABELS[r['status']]}”. Reload it before changing it.", "stale_status",
                   expected_status=r["status"])
    return r


def staff_transition(store: StoreId, agent_id: int, reference: str, target: str, *, expected_status: str,
                     message: str | None = None, note: str | None = None) -> dict[str, Any]:
    message = _check_text(message, "message") if message else None
    note = _check_text(note, "note") if note else None
    with store_connection(store) as conn, conn.transaction():
        r = _locked_for_staff(conn, reference, expected_status)
        if target not in TRANSITIONS[r["kind"]].get(r["status"], ()):
            raise _err(409, f"A {r['kind']} request that is “{STATUS_LABELS[r['status']]}” can’t be changed to "
                            f"“{STATUS_LABELS.get(target, target)}”.", "invalid_transition")
        if target in NEEDS_REASON and not message:
            raise _err(422, "Please tell the customer the reason.", "validation_error", message="required for this decision")
        eid = _set_status(conn, r, target, "agent", agent_id, message)
        if target == "assigned" and r["assigned_to"] is None:
            conn.execute("UPDATE care_requests SET assigned_to = %s WHERE id = %s", [agent_id, r["id"]])
        if note:
            _event(conn, r["id"], "note", None, None, "internal", "agent", agent_id, note)
        _queue_email(conn, r, eid)
        return _staff_view(conn, store, _row(conn, rid=r["id"]))


def staff_assign(store: StoreId, agent_id: int, reference: str, assignee_id: int) -> dict[str, Any]:
    with store_connection(store) as conn, conn.transaction():
        r = _locked_for_staff(conn, reference, None)
        if r["status"] in TERMINAL:
            raise _err(409, "This request is closed.", "invalid_state")
        who = conn.execute("SELECT id, full_name FROM customers WHERE id = %s AND role = 'agent'", [assignee_id]).fetchone()
        if who is None:   # only staff accounts of THIS store (this database) can be assigned
            raise _err(422, "That staff member doesn't exist in this store.", "validation_error", assignee_id="not a staff account here")
        conn.execute("UPDATE care_requests SET assigned_to = %s, updated_at = now() WHERE id = %s", [who["id"], r["id"]])
        _event(conn, r["id"], "assigned", None, None, "internal", "agent", agent_id, f"Assigned to {who['full_name']}")
        if r["kind"] == "escalation" and r["status"] == "open":
            eid = _set_status(conn, r, "assigned", "agent", agent_id)
            _queue_email(conn, r, eid)
        return _staff_view(conn, store, _row(conn, rid=r["id"]))


def staff_note(store: StoreId, agent_id: int, reference: str, body: str) -> dict[str, Any]:
    body = _check_text(body, "note")
    with store_connection(store) as conn, conn.transaction():
        r = _locked_for_staff(conn, reference, None)
        _event(conn, r["id"], "note", None, None, "internal", "agent", agent_id, body)
        return _staff_view(conn, store, _row(conn, rid=r["id"]))


def staff_message(store: StoreId, agent_id: int, reference: str, body: str) -> dict[str, Any]:
    body = _check_text(body, "message")
    with store_connection(store) as conn, conn.transaction():
        r = _locked_for_staff(conn, reference, None)
        eid = _event(conn, r["id"], "message", None, None, "customer", "agent", agent_id, body)
        _queue_email(conn, r, eid)
        return _staff_view(conn, store, _row(conn, rid=r["id"]))

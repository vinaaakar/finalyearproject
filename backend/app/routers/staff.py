"""Staff fulfilment API (Phase F). Agent accounts only, and only for the store their token was issued by
(`deps.require_agent` + the store binding checked in `deps`). Not an admin console: staff can list and view orders and
move them along the fulfilment path validated by the order state machine — nothing else (no edits to items, prices,
customers or payments)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import Field, field_validator

from .. import fulfilment
from .. import repositories as repo
from ..assistant.service import STATUS_LABELS, public_order, public_order_detail
from ..deps import StorePath, rate_limit, require_agent
from ..order_state import ORDER_TRANSITIONS
from ..schemas import Strict
from ..security import Principal

router = APIRouter(prefix="/api/stores/{store_id}/staff", tags=["staff"], dependencies=[Depends(rate_limit("default"))])

OrderNumber = Annotated[str, Path(pattern=r"^[A-Za-z]{2}-\d{5}$")]
Status = Literal["pending_payment", "processing", "shipped", "out_for_delivery", "delivered", "cancelled", "returned"]
Agent = Annotated[Principal, Depends(require_agent)]

# Which fulfilment actions the staff screen offers in each status (subset of ORDER_TRANSITIONS: staff never pay or
# cancel orders here; see app/fulfilment.py).
STAFF_ACTIONS = {"processing": ["ship"], "shipped": ["out_for_delivery", "deliver", "return"],
                 "out_for_delivery": ["deliver"], "delivered": ["return"]}
assert all(fulfilment.ACTIONS[a] in ORDER_TRANSITIONS[s] for s, acts in STAFF_ACTIONS.items() for a in acts)


class _Action(Strict):
    expected_status: Status
    note: str | None = Field(default=None, max_length=500)

    @field_validator("note")
    @classmethod
    def _clean_note(cls, v):
        v = (v or "").strip()
        return v or None


class ShipRequest(_Action):
    carrier: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9 &.\-]*$")
    tracking_number: str = Field(min_length=4, max_length=40, pattern=r"^[A-Za-z0-9\-]+$")
    tracking_url: str | None = Field(default=None, max_length=300, pattern=r"^https://[^\s<>\"']+$")
    estimated_delivery: date | None = None


class TrackingRequest(Strict):
    carrier: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9 &.\-]*$")
    tracking_number: str = Field(min_length=4, max_length=40, pattern=r"^[A-Za-z0-9\-]+$")
    tracking_url: str | None = Field(default=None, max_length=300, pattern=r"^https://[^\s<>\"']+$")
    note: str | None = Field(default=None, max_length=500)


class ReturnRequest(_Action):
    note: str = Field(min_length=3, max_length=500)   # a return must say why / what came back


def _staff_view(o: dict) -> dict:
    out = public_order_detail({**o, "history": []})
    out["customer_name"] = o["customer_name"]
    out["shipped_at"] = o["shipped_at"].isoformat() if o.get("shipped_at") else None
    out["delivered_at"] = o["delivered_at"].isoformat() if o.get("delivered_at") else None
    out["history"] = [{**h, "at": h["at"].isoformat(), "status_label": STATUS_LABELS.get(h["status"], h["status"])} for h in o["history"]]
    out["actions"] = STAFF_ACTIONS.get(o["status"], [])
    return out


@router.get("/orders")
def list_orders(store_id: StorePath, _agent: Agent,
                status: Annotated[list[Status] | None, Query()] = None,
                q: Annotated[str | None, Query(max_length=60)] = None,
                limit: Annotated[int, Query(ge=1, le=100)] = 25,
                offset: Annotated[int, Query(ge=0, le=100000)] = 0):
    rows, total = repo.list_staff_orders(store_id, statuses=status, query=(q or "").strip() or None, limit=limit, offset=offset)
    return {"orders": [{**public_order({**r, "items": []}), "customer_name": r["customer_name"], "item_count": r["item_count"],
                        "actions": STAFF_ACTIONS.get(r["status"], [])} for r in rows],
            "total": total, "limit": limit, "offset": offset,
            }


@router.get("/orders/{order_number}")
def get_order(store_id: StorePath, order_number: OrderNumber, _agent: Agent):
    o = repo.get_staff_order(store_id, order_number)
    if o is None:
        raise HTTPException(404, "Order not found.")
    return {"order": _staff_view(o)}


@router.post("/orders/{order_number}/ship")
def ship(store_id: StorePath, order_number: OrderNumber, body: ShipRequest, agent: Agent):
    o = fulfilment.apply_action(store_id, agent.customer_id, order_number, "ship", expected_status=body.expected_status,
                                carrier=body.carrier.strip(), tracking_number=body.tracking_number.upper(),
                                tracking_url=body.tracking_url, estimated_delivery=body.estimated_delivery, note=body.note)
    return {"order": _staff_view(o)}


@router.post("/orders/{order_number}/out-for-delivery")
def out_for_delivery(store_id: StorePath, order_number: OrderNumber, body: _Action, agent: Agent):
    o = fulfilment.apply_action(store_id, agent.customer_id, order_number, "out_for_delivery", expected_status=body.expected_status, note=body.note)
    return {"order": _staff_view(o)}


@router.post("/orders/{order_number}/deliver")
def deliver(store_id: StorePath, order_number: OrderNumber, body: _Action, agent: Agent):
    o = fulfilment.apply_action(store_id, agent.customer_id, order_number, "deliver", expected_status=body.expected_status, note=body.note)
    return {"order": _staff_view(o)}


@router.post("/orders/{order_number}/return")
def mark_returned(store_id: StorePath, order_number: OrderNumber, body: ReturnRequest, agent: Agent):
    o = fulfilment.apply_action(store_id, agent.customer_id, order_number, "return", expected_status=body.expected_status, note=body.note)
    return {"order": _staff_view(o)}


@router.put("/orders/{order_number}/tracking")
def correct_tracking(store_id: StorePath, order_number: OrderNumber, body: TrackingRequest, agent: Agent):
    o = fulfilment.update_tracking(store_id, agent.customer_id, order_number, carrier=body.carrier.strip(),
                                   tracking_number=body.tracking_number.upper(), tracking_url=body.tracking_url, note=body.note)
    return {"order": _staff_view(o)}

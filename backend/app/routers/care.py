"""Customer-care requests API: complaints, return requests, SIMULATED refund requests and human-help requests.

Customer routes act only for the signed-in customer of this store (deps.require_customer: the token is bound to one
store); staff routes only for an agent of this store (deps.require_agent). All rules live in app/care_requests.py.
Nothing here moves money: refund requests are a simulated workflow recorded for staff review.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Path, Query, Response
from pydantic import Field

from .. import care_requests as care
from ..deps import StorePath, rate_limit, require_agent, require_customer
from ..schemas import Strict
from ..security import Principal

router = APIRouter(prefix="/api/stores/{store_id}", tags=["customer care"], dependencies=[Depends(rate_limit("default"))])

Customer = Annotated[Principal, Depends(require_customer)]
Agent = Annotated[Principal, Depends(require_agent)]
Kind = Literal["complaint", "return", "refund", "escalation"]
Reference = Annotated[str, Path(pattern=r"^[A-Za-z]{2}-(CMP|RET|RFD|ESC|cmp|ret|rfd|esc)-\d{5,}$")]
StatusName = Literal["open", "requested", "under_review", "awaiting_customer", "assigned", "in_progress", "approved",
                     "rejected", "received", "inspected", "completed", "simulated_completed", "resolved", "closed", "withdrawn"]
Text = Annotated[str, Field(min_length=1, max_length=1000)]


class CareCreate(Strict):
    kind: Kind
    category: str = Field(pattern=r"^[a-z_]{2,40}$")
    description: Text
    order_number: str | None = Field(default=None, pattern=r"^[A-Za-z]{2}-\d{5}$")
    item_id: int | None = Field(default=None, ge=1)


class CareMessage(Strict):
    message: Text


class StaffTransition(Strict):
    status: StatusName
    expected_status: StatusName
    message: str | None = Field(default=None, max_length=1000)    # shown to the customer (required to reject / close)
    note: str | None = Field(default=None, max_length=1000)       # internal, never shown to the customer


class StaffAssign(Strict):
    assignee_id: int = Field(ge=1)


class StaffNote(Strict):
    body: Text


# ---- customer -------------------------------------------------------------------------------------------------------------
@router.get("/care/options")
def options(store_id: StorePath, principal: Customer, kind: Kind,
            order: Annotated[str | None, Query(pattern=r"^[A-Za-z]{2}-\d{5}$")] = None):
    return care.options(store_id, principal.customer_id, kind, order)


@router.post("/care/requests", status_code=201)
def create(store_id: StorePath, body: CareCreate, principal: Customer, response: Response,
           idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", pattern=r"^[A-Za-z0-9_-]{16,64}$")] = None):
    view, created = care.create(store_id, principal.customer_id, kind=body.kind, category=body.category,
                                description=body.description, order_number=body.order_number, item_id=body.item_id,
                                idempotency_key=idempotency_key)
    if not created:
        response.status_code = 200
    return {"request": view, "created": created}


@router.get("/care/requests")
def my_requests(store_id: StorePath, principal: Customer, kind: Kind | None = None):
    return {"requests": care.list_for_customer(store_id, principal.customer_id, kind)}


@router.get("/care/requests/{reference}")
def my_request(store_id: StorePath, reference: Reference, principal: Customer):
    return {"request": care.get_for_customer(store_id, principal.customer_id, reference)}


@router.post("/care/requests/{reference}/reply")
def reply(store_id: StorePath, reference: Reference, body: CareMessage, principal: Customer):
    return {"request": care.customer_reply(store_id, principal.customer_id, reference, body.message)}


@router.post("/care/requests/{reference}/withdraw")
def withdraw(store_id: StorePath, reference: Reference, principal: Customer):
    return {"request": care.withdraw(store_id, principal.customer_id, reference)}


# ---- staff (this store only) ------------------------------------------------------------------------------------------------
@router.get("/staff/care")
def staff_list(store_id: StorePath, _agent: Agent,
               kind: Annotated[list[Kind] | None, Query()] = None,
               status: Annotated[list[StatusName] | None, Query()] = None,
               q: Annotated[str | None, Query(max_length=30, pattern=r"^[A-Za-z0-9-]+$")] = None,
               date_from: date | None = None, date_to: date | None = None,
               limit: Annotated[int, Query(ge=1, le=100)] = 25, offset: Annotated[int, Query(ge=0, le=100000)] = 0):
    rows, total = care.staff_list(store_id, kinds=kind, statuses=status, query=q, date_from=date_from, date_to=date_to,
                                  limit=limit, offset=offset)
    return {"requests": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/staff/care/agents")
def staff_agents(store_id: StorePath, _agent: Agent):
    return {"agents": care.staff_agents(store_id)}


@router.get("/staff/care/{reference}")
def staff_get(store_id: StorePath, reference: Reference, _agent: Agent):
    return {"request": care.staff_get(store_id, reference)}


@router.post("/staff/care/{reference}/status")
def staff_status(store_id: StorePath, reference: Reference, body: StaffTransition, agent: Agent):
    return {"request": care.staff_transition(store_id, agent.customer_id, reference, body.status,
                                             expected_status=body.expected_status, message=body.message, note=body.note)}


@router.post("/staff/care/{reference}/assign")
def staff_assign(store_id: StorePath, reference: Reference, body: StaffAssign, agent: Agent):
    return {"request": care.staff_assign(store_id, agent.customer_id, reference, body.assignee_id)}


@router.post("/staff/care/{reference}/notes")
def staff_note(store_id: StorePath, reference: Reference, body: StaffNote, agent: Agent):
    return {"request": care.staff_note(store_id, agent.customer_id, reference, body.body)}


@router.post("/staff/care/{reference}/messages")
def staff_message(store_id: StorePath, reference: Reference, body: StaffNote, agent: Agent):
    return {"request": care.staff_message(store_id, agent.customer_id, reference, body.body)}

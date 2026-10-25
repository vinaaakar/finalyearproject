"""Login, profile and order endpoints. Order data is only returned to the owning
customer, or to a staff agent of the same store."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from .. import repositories as repo
from ..assistant.service import public_order
from ..deps import StorePath, rate_limit, require_agent, require_principal
from ..schemas import LoginRequest, LoginResponse
from ..security import DUMMY_PASSWORD_HASH, Principal, issue_token, verify_password

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stores/{store_id}", tags=["account"])

OrderNumber = Annotated[str, Path(pattern=r"^[A-Za-z]{2}-\d{5}$")]


@router.post("/auth/login", response_model=LoginResponse, dependencies=[Depends(rate_limit("login"))])
def login(store_id: StorePath, body: LoginRequest, request: Request):
    customer = repo.get_customer_by_email(store_id, body.email)
    # Always run one hash verification so response time does not reveal whether the email exists.
    valid = verify_password(body.password, customer["password_hash"] if customer else DUMMY_PASSWORD_HASH)
    if not customer or not valid:
        log.info("login failed store=%s", store_id.value)
        raise HTTPException(401, "Incorrect email or password.")
    settings = request.app.state.settings
    principal = Principal(customer_id=customer["id"], store=store_id, role=customer["role"], name=customer["full_name"])
    return LoginResponse(
        access_token=issue_token(principal, settings.secret_key, settings.token_ttl_minutes),
        expires_in=settings.token_ttl_minutes * 60,
        customer={"name": customer["full_name"], "email": customer["email"], "role": customer["role"]},
    )


@router.get("/me", dependencies=[Depends(rate_limit("default"))])
def me(store_id: StorePath, principal: Annotated[Principal, Depends(require_principal)]):
    customer = repo.get_customer_by_id(store_id, principal.customer_id)
    if customer is None:
        raise HTTPException(401, "Account no longer exists.")
    return {"name": customer["full_name"], "email": customer["email"], "role": customer["role"]}


@router.get("/orders", dependencies=[Depends(rate_limit("default"))])
def my_orders(store_id: StorePath, principal: Annotated[Principal, Depends(require_principal)]):
    return {"orders": [public_order(o) for o in repo.list_orders_for_customer(store_id, principal.customer_id)]}


@router.get("/orders/{order_number}", dependencies=[Depends(rate_limit("default"))])
def order_detail(store_id: StorePath, order_number: OrderNumber, principal: Annotated[Principal, Depends(require_principal)]):
    if principal.role == "agent":
        order = repo.get_order_by_number(store_id, order_number)
    else:
        order = repo.get_order_for_customer(store_id, order_number, principal.customer_id)
    if order is None:
        # Same response whether the order does not exist or belongs to someone else.
        raise HTTPException(404, "Order not found.")
    return {"order": public_order(order)}


@router.get("/admin/orders", dependencies=[Depends(rate_limit("default"))])
def admin_orders(store_id: StorePath, _agent: Annotated[Principal, Depends(require_agent)]):
    rows = repo.list_recent_orders(store_id)
    return {"orders": [{**public_order({**o, "items": []}), "customer_name": o["customer_name"]} for o in rows]}

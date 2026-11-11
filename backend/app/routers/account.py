"""Login, profile and order endpoints. Order data is only returned to the owning
customer, or to a staff agent of the same store."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response

from .. import repositories as repo
from ..assistant.service import public_order, public_order_detail
from ..deps import StorePath, clear_session_cookies, rate_limit, require_agent, require_principal, set_session_cookies
from ..notify import Email
from ..schemas import LoginRequest, LoginResponse, PasswordResetConfirm, PasswordResetRequest, RegisterRequest
from ..security import (DUMMY_PASSWORD_HASH, Principal, hash_opaque_token, hash_password, issue_token, new_opaque_token,
                        verify_password)
from ..stores import STORE_BRANDING

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stores/{store_id}", tags=["account"])

OrderNumber = Annotated[str, Path(pattern=r"^[A-Za-z]{2}-\d{5}$")]


@router.post("/auth/login", response_model=LoginResponse, dependencies=[Depends(rate_limit("login"))])
def login(store_id: StorePath, body: LoginRequest, request: Request, response: Response):
    customer = repo.get_customer_by_email(store_id, body.email)
    # Always run one hash verification so response time does not reveal whether the email exists.
    valid = verify_password(body.password, customer["password_hash"] if customer else DUMMY_PASSWORD_HASH)
    if not customer or not valid:
        log.info("login failed store=%s", store_id.value)
        raise HTTPException(401, "Incorrect email or password.")
    return _start_session(store_id, customer, request, response)


def _start_session(store_id, customer: dict, request: Request, response: Response) -> LoginResponse:
    """Create a server-side session row and an access token bound to it and to this store."""
    settings = request.app.state.settings
    session_id = new_opaque_token()
    repo.create_session(store_id, customer["id"], hash_opaque_token(session_id), settings.token_ttl_minutes)
    principal = Principal(customer_id=customer["id"], store=store_id, role=customer["role"], name=customer["full_name"], session_id=session_id)
    token = issue_token(principal, settings.secret_key, settings.token_ttl_minutes)
    who = {"name": customer["full_name"], "email": customer["email"], "role": customer["role"]}
    if settings.auth_cookies:
        csrf = set_session_cookies(response, store_id, token, settings)
        return LoginResponse(access_token=None, token_type="cookie", expires_in=settings.token_ttl_minutes * 60, customer=who, csrf_token=csrf)
    return LoginResponse(access_token=token, expires_in=settings.token_ttl_minutes * 60, customer=who)


@router.post("/auth/register", response_model=LoginResponse, status_code=201, dependencies=[Depends(rate_limit("account"))])
def register(store_id: StorePath, body: RegisterRequest, request: Request, response: Response):
    # Registration in one store never creates or reveals anything in the other store's database.
    customer = repo.create_customer(store_id, body.email, body.full_name, hash_password(body.password))
    if customer is None:
        raise HTTPException(409, "An account with this email already exists in this store. Sign in or reset your password.")
    log.info("account registered store=%s", store_id.value)
    return _start_session(store_id, customer, request, response)


@router.post("/auth/logout", status_code=204, dependencies=[Depends(rate_limit("default"))])
def logout(store_id: StorePath, principal: Annotated[Principal, Depends(require_principal)], response: Response):
    repo.revoke_session(store_id, hash_opaque_token(principal.session_id))
    clear_session_cookies(response, store_id)


@router.post("/auth/logout-all", status_code=204, dependencies=[Depends(rate_limit("default"))])
def logout_everywhere(store_id: StorePath, principal: Annotated[Principal, Depends(require_principal)], response: Response):
    """Sign out every session of this account in this store (lost phone, shared computer)."""
    repo.revoke_all_sessions(store_id, principal.customer_id)
    clear_session_cookies(response, store_id)


RESET_ACCEPTED = {"message": "If an account exists for that email, we've sent a link to reset the password."}


@router.post("/auth/password-reset/request", status_code=202, dependencies=[Depends(rate_limit("account"))])
def password_reset_request(store_id: StorePath, body: PasswordResetRequest, request: Request):
    """Always answers the same way, so it cannot be used to discover which emails have accounts."""
    settings = request.app.state.settings
    customer = repo.get_customer_by_email(store_id, body.email)
    if customer is not None:
        token = new_opaque_token()
        repo.create_password_reset(store_id, customer["id"], hash_opaque_token(token), settings.password_reset_ttl_minutes)
        # The token goes in the URL fragment so it is not sent to servers in requests or Referer headers.
        link = f"{settings.store_public_urls[store_id.value]}/reset-password#token={token}"
        brand = STORE_BRANDING[store_id]["name"]
        request.app.state.mailer.send(store_id.value, Email(
            to=customer["email"],
            subject=f"Reset your {brand} password",
            body=(f"Hi {customer['full_name']},\n\nUse this link within {settings.password_reset_ttl_minutes} minutes to choose a new "
                  f"{brand} password:\n{link}\n\nIf you didn't ask for this, you can ignore this email."),
        ))
    return RESET_ACCEPTED


@router.post("/auth/password-reset/confirm", dependencies=[Depends(rate_limit("account"))])
def password_reset_confirm(store_id: StorePath, body: PasswordResetConfirm):
    customer_id = repo.consume_password_reset(store_id, hash_opaque_token(body.token), hash_password(body.new_password))
    if customer_id is None:
        raise HTTPException(400, "This reset link is invalid or has expired. Please request a new one.")
    log.info("password reset completed store=%s", store_id.value)
    return {"message": "Your password has been changed. Please sign in with your new password."}


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
    order = repo.get_order_detail(store_id, order_number, None if principal.role == "agent" else principal.customer_id)
    if order is None:
        # Same response whether the order does not exist or belongs to someone else.
        raise HTTPException(404, "Order not found.")
    return {"order": public_order_detail(order)}


@router.get("/admin/orders", dependencies=[Depends(rate_limit("default"))])
def admin_orders(store_id: StorePath, _agent: Annotated[Principal, Depends(require_agent)]):
    rows = repo.list_recent_orders(store_id)
    return {"orders": [{**public_order({**o, "items": []}), "customer_name": o["customer_name"]} for o in rows]}

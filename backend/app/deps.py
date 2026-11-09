"""Shared request dependencies: settings, auth principal, role checks, rate limits."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Path, Request

from . import repositories as repo
from .commerce import CartOwner
from .config import Settings
from .ratelimit import limiter
from .security import Principal, TokenError, decode_token, hash_opaque_token
from .stores import StoreId

StorePath = Annotated[StoreId, Path(description="store-a or store-b")]


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(bucket: str):
    def dependency(request: Request) -> None:
        s: Settings = request.app.state.settings
        limit = {
            "chat": s.rate_limit_chat_per_min,
            "login": s.rate_limit_login_per_min,
            "account": s.rate_limit_login_per_min,
        }.get(bucket, s.rate_limit_default_per_min)
        retry = limiter.hit(bucket, client_key(request), limit)
        if retry is not None:
            raise HTTPException(429, "Too many requests. Please slow down.", headers={"Retry-After": str(int(retry) + 1)})

    return dependency


def optional_principal(
    store_id: StorePath,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Invalid authorization header", headers={"WWW-Authenticate": "Bearer"})
    try:
        principal = decode_token(token, request.app.state.settings.secret_key)
    except TokenError:
        raise HTTPException(401, "Session expired or invalid. Please sign in again.", headers={"WWW-Authenticate": "Bearer"})
    if principal.store != store_id:
        # A Store A session can never be used against Store B (and vice versa).
        raise HTTPException(403, "This session belongs to a different store.")
    # The token must also match a live server-side session (sign-out and password resets revoke them).
    if not principal.session_id or not repo.session_is_active(store_id, hash_opaque_token(principal.session_id), principal.customer_id):
        raise HTTPException(401, "Session expired or invalid. Please sign in again.", headers={"WWW-Authenticate": "Bearer"})
    return principal


def require_principal(principal: Annotated[Principal | None, Depends(optional_principal)]) -> Principal:
    if principal is None:
        raise HTTPException(401, "Please sign in to continue.", headers={"WWW-Authenticate": "Bearer"})
    return principal


def require_agent(principal: Annotated[Principal, Depends(require_principal)]) -> Principal:
    if principal.role != "agent":
        raise HTTPException(403, "Staff access required.")
    return principal


def require_customer(principal: Annotated[Principal, Depends(require_principal)]) -> Principal:
    """Shopping (cart, checkout, payment) is for customer accounts; staff accounts cannot place orders."""
    if principal.role != "customer":
        raise HTTPException(403, "Staff accounts cannot shop. Please use a customer account.")
    return principal


CART_TOKEN_PATTERN = r"^[A-Za-z0-9_-]{32,64}$"


def cart_token_header(x_cart_token: Annotated[str | None, Header(pattern=CART_TOKEN_PATTERN)] = None) -> str | None:
    return x_cart_token


def cart_owner(
    principal: Annotated[Principal | None, Depends(optional_principal)],
    guest_token: Annotated[str | None, Depends(cart_token_header)],
) -> CartOwner:
    if principal is not None:
        if principal.role != "customer":
            raise HTTPException(403, "Staff accounts cannot shop. Please use a customer account.")
        return CartOwner(customer_id=principal.customer_id)
    return CartOwner(guest_hash=hash_opaque_token(guest_token) if guest_token else None)

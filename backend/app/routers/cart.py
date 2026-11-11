"""Shopping cart. Guests are identified by an opaque X-Cart-Token; signed-in customers by their session.
The server validates every quantity against current stock and computes all totals."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response

from .. import commerce
from ..commerce import CartOwner
from ..deps import StorePath, cart_owner, cart_token_header, rate_limit, require_customer
from ..schemas import CartItemAdd, CartItemUpdate
from ..security import Principal, hash_opaque_token, new_opaque_token

router = APIRouter(prefix="/api/stores/{store_id}/cart", tags=["cart"], dependencies=[Depends(rate_limit("default"))])

SlugPath = Annotated[str, Path(pattern=r"^[a-z0-9-]{1,80}$")]


def _cart(store_id, owner: CartOwner, request: Request, country: str | None = None) -> dict:
    """The cart priced for the delivery country (default: the store's market — India, in ₹, for this project).
    India: approved INR prices only (never converted) and no shipping figure until checkout knows the address.
    A US-market store without `country` gets exactly the original cart (catalogue prices, US rates)."""
    market = request.app.state.settings.store_markets.get(store_id.value, "US")
    country = country or market
    if country == "US" and market == "US":
        return commerce.get_cart(store_id, owner)
    if country == "US":
        from ..shipping_zones import rates_for
        return commerce.get_cart(store_id, owner, rates=rates_for(store_id, request.app.state.settings.shipping_config_dir, "US"), country="US")
    cart = commerce.get_cart(store_id, owner, rates=None, country=country)
    from ..shipping_zones import configured
    if configured(store_id, request.app.state.settings.shipping_config_dir, country):
        # Rates exist; they depend on the address, so delivery is priced at checkout (not "unavailable").
        cart["shipping_problem"] = "Delivery is calculated at checkout from your address."
        cart["shipping_at_checkout"] = True
    return cart


@router.get("")
def get_cart(store_id: StorePath, owner: Annotated[CartOwner, Depends(cart_owner)], request: Request,
             country: Annotated[Literal["US", "IN"] | None, Query()] = None):
    return {"cart": _cart(store_id, owner, request, country)}


@router.post("/items")
def add_item(store_id: StorePath, body: CartItemAdd, owner: Annotated[CartOwner, Depends(cart_owner)], response: Response,
             request: Request):
    new_token = None
    if owner.customer_id is None and owner.guest_hash is None:
        # First item for a new guest: issue a cart token (only its hash is stored).
        new_token = new_opaque_token()
        owner = CartOwner(guest_hash=hash_opaque_token(new_token))
    commerce.set_item(store_id, owner, body.slug, body.quantity, add=True)
    result = {"cart": _cart(store_id, owner, request)}
    if new_token:
        result["cart_token"] = new_token
    return result


@router.put("/items/{slug}")
def update_item(store_id: StorePath, slug: SlugPath, body: CartItemUpdate, owner: Annotated[CartOwner, Depends(cart_owner)],
                request: Request):
    if owner.customer_id is None and owner.guest_hash is None:
        raise HTTPException(404, "Cart not found.")
    commerce.set_item(store_id, owner, slug, body.quantity)
    return {"cart": _cart(store_id, owner, request)}


@router.delete("/items/{slug}")
def remove_item(store_id: StorePath, slug: SlugPath, owner: Annotated[CartOwner, Depends(cart_owner)], request: Request):
    if owner.customer_id is not None or owner.guest_hash is not None:
        commerce.set_item(store_id, owner, slug, 0)
    return {"cart": _cart(store_id, owner, request)}


@router.post("/merge")
def merge(store_id: StorePath, principal: Annotated[Principal, Depends(require_customer)],
          guest_token: Annotated[str | None, Depends(cart_token_header)], request: Request):
    """Called after sign-in: moves the guest cart (if any) into the customer's cart."""
    if guest_token:
        commerce.merge_guest_cart(store_id, hash_opaque_token(guest_token), principal.customer_id)
    return {"cart": _cart(store_id, CartOwner(customer_id=principal.customer_id), request)}

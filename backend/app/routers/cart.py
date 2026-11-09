"""Shopping cart. Guests are identified by an opaque X-Cart-Token; signed-in customers by their session.
The server validates every quantity against current stock and computes all totals."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response

from .. import commerce
from ..commerce import CartOwner
from ..deps import StorePath, cart_owner, cart_token_header, rate_limit, require_customer
from ..schemas import CartItemAdd, CartItemUpdate
from ..security import Principal, hash_opaque_token, new_opaque_token

router = APIRouter(prefix="/api/stores/{store_id}/cart", tags=["cart"], dependencies=[Depends(rate_limit("default"))])

SlugPath = Annotated[str, Path(pattern=r"^[a-z0-9-]{1,80}$")]


@router.get("")
def get_cart(store_id: StorePath, owner: Annotated[CartOwner, Depends(cart_owner)]):
    return {"cart": commerce.get_cart(store_id, owner)}


@router.post("/items")
def add_item(store_id: StorePath, body: CartItemAdd, owner: Annotated[CartOwner, Depends(cart_owner)], response: Response):
    new_token = None
    if owner.customer_id is None and owner.guest_hash is None:
        # First item for a new guest: issue a cart token (only its hash is stored).
        new_token = new_opaque_token()
        owner = CartOwner(guest_hash=hash_opaque_token(new_token))
    cart = commerce.set_item(store_id, owner, body.slug, body.quantity, add=True)
    result = {"cart": cart}
    if new_token:
        result["cart_token"] = new_token
    return result


@router.put("/items/{slug}")
def update_item(store_id: StorePath, slug: SlugPath, body: CartItemUpdate, owner: Annotated[CartOwner, Depends(cart_owner)]):
    if owner.customer_id is None and owner.guest_hash is None:
        raise HTTPException(404, "Cart not found.")
    return {"cart": commerce.set_item(store_id, owner, slug, body.quantity)}


@router.delete("/items/{slug}")
def remove_item(store_id: StorePath, slug: SlugPath, owner: Annotated[CartOwner, Depends(cart_owner)]):
    if owner.customer_id is None and owner.guest_hash is None:
        return {"cart": commerce.get_cart(store_id, owner)}
    return {"cart": commerce.set_item(store_id, owner, slug, 0)}


@router.post("/merge")
def merge(store_id: StorePath, principal: Annotated[Principal, Depends(require_customer)],
          guest_token: Annotated[str | None, Depends(cart_token_header)]):
    """Called after sign-in: moves the guest cart (if any) into the customer's cart."""
    if not guest_token:
        return {"cart": commerce.get_cart(store_id, CartOwner(customer_id=principal.customer_id))}
    return {"cart": commerce.merge_guest_cart(store_id, hash_opaque_token(guest_token), principal.customer_id)}

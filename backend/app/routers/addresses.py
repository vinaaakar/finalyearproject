"""Customer saved addresses (Address Book).
All endpoints require an authenticated customer session of the specified store.
Isolation between customers and stores is strictly enforced."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Response

from .. import commerce
from .. import repositories as repo
from ..deps import StorePath, rate_limit, require_customer
from ..schemas import AddressCreate, AddressUpdate
from ..security import Principal

router = APIRouter(prefix="/api/stores/{store_id}/addresses", tags=["addresses"], dependencies=[Depends(rate_limit("default"))])
Customer = Annotated[Principal, Depends(require_customer)]
AddressId = Annotated[int, Path(ge=1)]


def public_address(addr: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": addr["id"],
        "label": addr["label"],
        "full_name": addr["full_name"],
        "line1": addr["line1"],
        "line2": addr.get("line2"),
        "city": addr["city"],
        "region": addr["region"],
        "postal_code": addr["postal_code"],
        "country": addr["country"],
        "phone": addr.get("phone"),
        "is_default": bool(addr["is_default"]),
        "created_at": addr["created_at"].isoformat() if hasattr(addr.get("created_at"), "isoformat") else addr.get("created_at"),
        "updated_at": addr["updated_at"].isoformat() if hasattr(addr.get("updated_at"), "isoformat") else addr.get("updated_at"),
    }


@router.get("")
def list_addresses(store_id: StorePath, principal: Customer):
    """List all saved addresses for the authenticated customer, default address first."""
    rows = repo.list_addresses(store_id, principal.customer_id)
    return {"addresses": [public_address(r) for r in rows]}


@router.get("/default")
def get_default_address(store_id: StorePath, principal: Customer):
    """Get the customer's saved default address, or null if none is saved."""
    addr = repo.get_default_address(store_id, principal.customer_id)
    return {"address": public_address(addr) if addr else None}


@router.post("", status_code=201)
def create_address(store_id: StorePath, body: AddressCreate, principal: Customer):
    """Save a new address to the customer's account."""
    validated = commerce.validate_address(store_id, body.model_dump())
    row = repo.create_address(
        store_id,
        principal.customer_id,
        validated,
        is_default=body.is_default,
        label=body.label,
    )
    return {"address": public_address(row)}


@router.get("/{address_id}")
def get_address(store_id: StorePath, address_id: AddressId, principal: Customer):
    """Get a single address by id. Scoped to the customer."""
    addr = repo.get_address(store_id, principal.customer_id, address_id)
    if addr is None:
        raise HTTPException(404, "Address not found.")
    return {"address": public_address(addr)}


@router.put("/{address_id}")
def update_address(store_id: StorePath, address_id: AddressId, body: AddressUpdate, principal: Customer):
    """Update a saved address. Validates market rules on modified address fields."""
    existing = repo.get_address(store_id, principal.customer_id, address_id)
    if existing is None:
        raise HTTPException(404, "Address not found.")

    updates = body.model_dump(exclude_unset=True)
    # Check if address fields changed that need market validation
    merged = {
        "full_name": updates.get("full_name", existing["full_name"]),
        "line1": updates.get("line1", existing["line1"]),
        "line2": updates.get("line2", existing["line2"]),
        "city": updates.get("city", existing["city"]),
        "region": updates.get("region", existing["region"]),
        "postal_code": updates.get("postal_code", existing["postal_code"]),
        "country": updates.get("country", existing["country"]),
        "phone": updates.get("phone", existing["phone"]),
    }
    validated = commerce.validate_address(store_id, merged)
    for k, v in validated.items():
        if k in updates:
            updates[k] = v

    row = repo.update_address(store_id, principal.customer_id, address_id, updates)
    if row is None:
        raise HTTPException(404, "Address not found.")
    return {"address": public_address(row)}


@router.put("/{address_id}/default")
def set_default(store_id: StorePath, address_id: AddressId, principal: Customer):
    """Set an address as the customer's default address."""
    ok = repo.set_default_address(store_id, principal.customer_id, address_id)
    if not ok:
        raise HTTPException(404, "Address not found.")
    return {"ok": True}


@router.delete("/{address_id}", status_code=204)
def delete_address(store_id: StorePath, address_id: AddressId, principal: Customer, response: Response):
    """Delete a saved address. If default, the most recently updated remaining address becomes default."""
    ok = repo.delete_address(store_id, principal.customer_id, address_id)
    if not ok:
        raise HTTPException(404, "Address not found.")

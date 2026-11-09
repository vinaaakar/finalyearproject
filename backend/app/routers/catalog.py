from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from .. import repositories as repo
from ..assistant.service import ORDER_PREFIX, public_product
from ..deps import StorePath, rate_limit
from ..stores import STORE_BRANDING

router = APIRouter(prefix="/api/stores/{store_id}", tags=["catalog"], dependencies=[Depends(rate_limit("default"))])


@router.get("")
def store_info(store_id: StorePath):
    profile = repo.get_store_profile(store_id)
    if profile is None:
        raise HTTPException(503, "Store data has not been initialised.")
    return {
        "id": store_id.value,
        **STORE_BRANDING[store_id],
        "support_email": profile["support_email"],
        "support_hours": profile["support_hours"],
        "currency": profile["currency"],
        "order_number_prefix": ORDER_PREFIX[store_id],
        "policies": repo.get_policies(store_id),
    }


@router.get("/categories")
def categories(store_id: StorePath):
    return {"categories": repo.list_categories(store_id)}


@router.get("/products")
def products(
    store_id: StorePath,
    category: Annotated[str | None, Query(max_length=60)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
):
    query = (q or "").strip()
    if query:
        rows = repo.search_catalog(store_id, query, category=category or None, limit=limit, offset=offset)
    else:
        rows = repo.list_products(store_id, category=category or None, limit=limit, offset=offset)
    return {"products": [public_product(p) for p in rows]}


@router.get("/products/{slug}")
def product_detail(store_id: StorePath, slug: Annotated[str, Path(pattern=r"^[a-z0-9-]{1,80}$")]):
    product = repo.get_product_by_slug(store_id, slug)
    if product is None:
        raise HTTPException(404, "Product not found.")
    return {"product": public_product(product)}

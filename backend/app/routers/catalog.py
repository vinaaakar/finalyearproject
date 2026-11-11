from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from .. import repositories as repo
from ..assistant.service import ORDER_PREFIX, public_product
from ..market_policies import policies_for
from ..pricing import localize, selling_currency
from ..assistant.truth import verified_policies
from ..deps import StorePath, rate_limit
from ..stores import STORE_BRANDING

router = APIRouter(prefix="/api/stores/{store_id}", tags=["catalog"], dependencies=[Depends(rate_limit("default"))])


@router.get("")
def store_info(store_id: StorePath, request: Request, lang: Annotated[str, Query(pattern="^(en|ta|hi)$")] = "en"):
    profile = repo.get_store_profile(store_id)
    if profile is None:
        raise HTTPException(503, "Store data has not been initialised.")
    return {
        "id": store_id.value,
        **STORE_BRANDING[store_id],
        "support_email": profile["support_email"],
        "support_hours": profile["support_hours"],
        "currency": selling_currency(request.app.state.settings.store_markets, store_id),
        "order_number_prefix": ORDER_PREFIX[store_id],
        # Only what this system can honour: payment text from the real provider, unsupported sentences removed
        # (the same filter the assistant uses), in the requested language where a translation exists.
        "policies": verified_policies(policies_for(store_id, request.app.state.settings, lang, repo.get_policies(store_id, lang)),
                                      request.app.state.payments, lang),
        "policy_language": lang,
    }


@router.get("/market")
def market(store_id: StorePath, request: Request):
    """Address rules, regions, currency and whether delivery is configured — the storefront's checkout form is built
    from this, so the browser and the server never disagree about what is valid."""
    from ..markets import get_market
    from ..shipping_zones import configured
    s = request.app.state.settings
    m = get_market(s.store_markets[store_id.value])
    return {"market": {**m.public(), "shipping_configured": configured(store_id, s.shipping_config_dir, m.code)}}


@router.get("/categories")
def categories(store_id: StorePath):
    return {"categories": repo.list_categories(store_id)}


def _with_prices(store_id, rows: list[dict], request: Request) -> list[dict]:
    """Products priced in the store's selling currency (INR for India): the owner-approved price, or null where none is
    approved — never the USD catalogue amount, never converted. `prices` lists that one currency (older pages read it)."""
    currency = selling_currency(request.app.state.settings.store_markets, store_id)
    out = []
    for p in localize(store_id, rows, currency):
        view = {k: v for k, v in public_product(p).items()}
        view["prices"] = {currency: None if p["price_cents"] is None else {"minor": p["price_cents"], "display": view["price"]}}
        out.append(view)
    return out


@router.get("/products")
def products(
    store_id: StorePath,
    category: Annotated[str | None, Query(max_length=60)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    request: Request = None,
):
    query = (q or "").strip()
    if query:
        rows = repo.search_catalog(store_id, query, category=category or None, limit=limit, offset=offset)
    else:
        rows = repo.list_products(store_id, category=category or None, limit=limit, offset=offset)
    return {"products": _with_prices(store_id, rows, request)}


@router.get("/products/{slug}")
def product_detail(store_id: StorePath, slug: Annotated[str, Path(pattern=r"^[a-z0-9-]{1,80}$")], request: Request):
    product = repo.get_product_by_slug(store_id, slug)
    if product is None:
        raise HTTPException(404, "Product not found.")
    return {"product": _with_prices(store_id, [product], request)[0]}

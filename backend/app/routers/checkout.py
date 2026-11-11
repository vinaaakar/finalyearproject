"""Checkout and payments. All amounts are computed on the server; payment success is
confirmed with the payment provider, never taken from the client."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, Response

from .. import commerce
from ..assistant.service import public_order
from ..commerce import CartOwner
from .. import repositories as repo
from ..deps import StorePath, rate_limit, require_customer
from ..markets import MARKETS
from ..pricing import currency_for_country, price_list_status
from ..shipping_zones import configured, rates_for
from ..schemas import CheckoutRequest, QuoteRequest, SandboxCompleteRequest
from ..security import Principal

router = APIRouter(prefix="/api/stores/{store_id}", tags=["checkout"], dependencies=[Depends(rate_limit("default"))])

OrderNumber = Annotated[str, Path(pattern=r"^[A-Za-z]{2}-\d{5}$")]
Customer = Annotated[Principal, Depends(require_customer)]


@router.get("/checkout/address-options")
def address_options(store_id: StorePath, principal: Customer, request: Request):
    """Countries this store's checkout offers, each with its address rules (regions, postal format, phone), whether
    delivery rates exist for it, and the default: the customer's last order country, else the store's default."""
    s = request.app.state.settings
    prices = price_list_status(store_id)["currencies"]
    countries = [{**MARKETS[c].public(), "shipping_configured": configured(store_id, s.shipping_config_dir, c),
                  "currency": currency_for_country(store_id, c),
                  "prices_configured": prices.get(currency_for_country(store_id, c), {}).get("complete", False)}
                 for c in s.checkout_countries]
    last = repo.last_order_country(store_id, principal.customer_id)
    default = last if last in s.checkout_countries else s.default_checkout_country.get(store_id.value, s.checkout_countries[0])
    return {"countries": countries, "default_country": default}


@router.post("/checkout/quote")
def quote(store_id: StorePath, body: QuoteRequest, principal: Customer, request: Request):
    """Order review: the server's prices, shipping and total for the current cart — for the destination if given
    (no destination = the store's US rates, as before)."""
    owner = CartOwner(customer_id=principal.customer_id)
    market = request.app.state.settings.store_markets.get(store_id.value, "US")
    if body.destination is None and market == "US":
        return {"cart": commerce.get_cart(store_id, owner, body.shipping_method)}
    from ..schemas import Destination
    d = body.destination or Destination(country=market)     # India store: priced in ₹, shipping once the address is known
    rates = rates_for(store_id, request.app.state.settings.shipping_config_dir, d.country, d.region, d.postal_code)
    method = body.shipping_method if rates and (body.shipping_method == "standard" or rates.get("expedited_shipping_cents") is not None) else "standard"
    return {"cart": commerce.get_cart(store_id, owner, method, rates=rates, country=d.country)}


@router.post("/checkout", status_code=201)
def checkout(
    store_id: StorePath,
    body: CheckoutRequest,
    principal: Customer,
    response: Response,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", pattern=r"^[A-Za-z0-9_-]{16,64}$")],
):
    a = body.shipping
    rates = rates_for(store_id, request.app.state.settings.shipping_config_dir, a.country, a.region, a.postal_code)
    order, created = commerce.place_order(store_id, principal.customer_id, idempotency_key, a.model_dump(),
                                          body.shipping_method, body.expected_total_cents, rates=rates)
    if not created:
        response.status_code = 200
    return {"order": public_order(order), "created": created}


@router.post("/orders/{order_number}/cancel")
def cancel(store_id: StorePath, order_number: OrderNumber, principal: Customer):
    return {"order": public_order(commerce.cancel_pending_order(store_id, principal.customer_id, order_number))}


@router.get("/orders/{order_number}/payment")
def payment_status(store_id: StorePath, order_number: OrderNumber, principal: Customer, request: Request):
    return {"payment": commerce.latest_payment(store_id, principal.customer_id, order_number, request.app.state.payments)}


@router.post("/orders/{order_number}/payments")
def start_payment(store_id: StorePath, order_number: OrderNumber, principal: Customer, request: Request):
    return {"payment": commerce.start_payment(store_id, principal.customer_id, order_number, request.app.state.payments)}


@router.post("/orders/{order_number}/payments/verify")
def verify_payment(store_id: StorePath, order_number: OrderNumber, principal: Customer, request: Request):
    """Takes no status from the client: the server asks the payment provider."""
    result = commerce.verify_payment(store_id, principal.customer_id, order_number, request.app.state.payments)
    return {"order": public_order(result["order"]), "payment": result["payment"]}


@router.post("/payments/sandbox/{reference}/complete")
def sandbox_complete(store_id: StorePath, reference: Annotated[str, Path(pattern=r"^sbx_[A-Za-z0-9_-]{10,40}$")],
                     body: SandboxCompleteRequest, principal: Customer, request: Request):
    """SANDBOX ONLY — stands in for the provider's hosted payment page. It changes only the
    sandbox provider's record; the order changes only when /payments/verify asks the provider."""
    provider = request.app.state.payments
    if not provider.sandbox:
        raise HTTPException(404, "Not found.")
    if not commerce.pending_payment_ref_owned_by(store_id, principal.customer_id, reference):
        raise HTTPException(404, "Payment not found.")
    if not provider.complete(store_id, reference, body.outcome):
        raise HTTPException(409, "This test payment has already been completed.")
    return {"sandbox": True, "message": "Test payment completed at the sandbox provider. No real money moved."}

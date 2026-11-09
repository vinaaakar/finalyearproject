"""Checkout and payments. All amounts are computed on the server; payment success is
confirmed with the payment provider, never taken from the client."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, Response

from .. import commerce
from ..assistant.service import public_order
from ..commerce import CartOwner
from ..deps import StorePath, rate_limit, require_customer
from ..schemas import CheckoutRequest, QuoteRequest, SandboxCompleteRequest
from ..security import Principal

router = APIRouter(prefix="/api/stores/{store_id}", tags=["checkout"], dependencies=[Depends(rate_limit("default"))])

OrderNumber = Annotated[str, Path(pattern=r"^[A-Za-z]{2}-\d{5}$")]
Customer = Annotated[Principal, Depends(require_customer)]


@router.post("/checkout/quote")
def quote(store_id: StorePath, body: QuoteRequest, principal: Customer):
    """Order review: the server's prices, shipping and total for the current cart."""
    return {"cart": commerce.get_cart(store_id, CartOwner(customer_id=principal.customer_id), body.shipping_method)}


@router.post("/checkout", status_code=201)
def checkout(
    store_id: StorePath,
    body: CheckoutRequest,
    principal: Customer,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", pattern=r"^[A-Za-z0-9_-]{16,64}$")],
):
    order, created = commerce.place_order(store_id, principal.customer_id, idempotency_key, body.shipping.model_dump(),
                                          body.shipping_method, body.expected_total_cents)
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

from __future__ import annotations

import time
from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool

from ..assistant.language import verify_receipt
from ..commerce import CartOwner
from ..deps import StorePath, cart_token_header, optional_principal, rate_limit
from ..schemas import ChatRequest, ChatResponse
from ..security import Principal, hash_opaque_token

router = APIRouter(prefix="/api/stores/{store_id}", tags=["assistant"])


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(rate_limit("chat"))])
async def chat(
    store_id: StorePath,
    body: ChatRequest,
    request: Request,
    principal: Annotated[Principal | None, Depends(optional_principal)],
    guest_cart: Annotated[str | None, Depends(cart_token_header)],
):
    assistant = request.app.state.assistant
    history = [t.model_dump() for t in body.history]
    # Identity comes only from the verified session or the shopper's own cart token, never from the message text.
    if principal is not None:
        owner = CartOwner(customer_id=principal.customer_id) if principal.role == "customer" else None
    else:
        owner = CartOwner(guest_hash=hash_opaque_token(guest_cart)) if guest_cart else None
    # Acoustic language evidence is accepted only from a receipt this server signed for this exact text.
    acoustic = verify_receipt(request.app.state.settings.secret_key, body.speech_receipt, store_id.value, body.message)
    started = time.perf_counter()
    result = await run_in_threadpool(partial(assistant.answer, store_id, body.message, principal, history, owner,
                                             conversation_language=body.conversation_language, acoustic=acoustic,
                                             language_override=body.language_override, care_draft=body.care_draft))
    result.timing = {**(result.timing or {}), "total_ms": round((time.perf_counter() - started) * 1000)}
    return ChatResponse(**result.__dict__)

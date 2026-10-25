from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool

from ..deps import StorePath, optional_principal, rate_limit
from ..schemas import ChatRequest, ChatResponse
from ..security import Principal

router = APIRouter(prefix="/api/stores/{store_id}", tags=["assistant"])


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(rate_limit("chat"))])
async def chat(
    store_id: StorePath,
    body: ChatRequest,
    request: Request,
    principal: Annotated[Principal | None, Depends(optional_principal)],
):
    assistant = request.app.state.assistant
    history = [t.model_dump() for t in body.history]
    result = await run_in_threadpool(assistant.answer, store_id, body.message, principal, history)
    return ChatResponse(**result.__dict__)

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.concurrency import run_in_threadpool

from ..deps import StorePath, rate_limit
from ..phone.simulator import SimulatorProvider
from ..schemas import PhoneTurnRequest
from ..speech.adapters import capabilities

router = APIRouter(tags=["voice & phone"], dependencies=[Depends(rate_limit("default"))])
simulator = SimulatorProvider()

CallId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{8,40}$")]


@router.get("/api/speech/capabilities")
def speech_capabilities(request: Request):
    return capabilities(request.app.state.stt, request.app.state.tts)


@router.post("/api/phone/simulator/{store_id}/calls")
def simulator_start_call(store_id: StorePath, request: Request):
    return simulator.render(request.app.state.calls.start(store_id))


@router.post("/api/phone/simulator/calls/{call_id}/turns", dependencies=[Depends(rate_limit("chat"))])
async def simulator_turn(call_id: CallId, body: PhoneTurnRequest, request: Request):
    inbound = simulator.parse_inbound({"call_id": call_id, **body.model_dump()})
    outbound = await run_in_threadpool(request.app.state.calls.handle, inbound)
    if outbound is None:
        raise HTTPException(404, "Call not found or already ended.")
    return simulator.render(outbound)

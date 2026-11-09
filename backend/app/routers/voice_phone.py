from __future__ import annotations

from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.concurrency import run_in_threadpool

from ..deps import StorePath, client_key, rate_limit
from ..phone.simulator import SimulatorProvider
from ..schemas import PhoneTurnRequest, SynthesizeRequest
from ..speech.adapters import MAX_AUDIO_BYTES, SpeechError, capabilities
from ..assistant.language import speech_receipt
from ..stores import ORDER_PREFIX

router = APIRouter(tags=["voice & phone"], dependencies=[Depends(rate_limit("default"))])
simulator = SimulatorProvider()

CallId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{8,40}$")]


@router.get("/api/speech/capabilities")
def speech_capabilities(request: Request):
    s = request.app.state.settings
    return capabilities(request.app.state.stt, request.app.state.tts, s.speech_languages, s.speech_default_language)


@router.post("/api/stores/{store_id}/speech/transcribe", dependencies=[Depends(rate_limit("chat"))])
async def transcribe(store_id: StorePath, request: Request,
                     language: Annotated[str, Query(pattern=r"^(auto|ta|en|hi)$")] = "auto"):
    """Local speech-to-text. Body: a 16-bit PCM WAV recording (max 30 s). Audio is not stored or logged.
    language=auto identifies Tamil / English / Hindi (restricted to SPEECH_LANGUAGES) and falls back to the
    default language (Tamil unless configured otherwise) when unsure."""
    stt = request.app.state.stt
    if not stt.available:
        raise HTTPException(503, "Server speech recognition is not configured.")
    mime = request.headers.get("content-type", "").split(";")[0].strip().lower()
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "That recording is too long.")
    audio = bytearray()
    async for chunk in request.stream():
        audio += chunk
        if len(audio) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "That recording is too long.")
    prefix = ORDER_PREFIX[store_id].rstrip("-")
    # Biases recognition toward this store's order-number format (e.g. "SA-10001").
    prompt = f"Order numbers look like {prefix}-10001: two letters, a dash, five digits."
    try:
        if hasattr(stt, "recognize"):
            t = await run_in_threadpool(stt.recognize, bytes(audio), mime, language, prompt)
            text, detected, prob, uncertain = t.text, t.detected_language, t.language_probability, t.uncertain
        else:
            text = await run_in_threadpool(stt.transcribe, bytes(audio), mime, "en" if language == "auto" else language, prompt)
            detected, prob, uncertain = None, None, False
    except SpeechError as exc:
        raise HTTPException(400, str(exc))
    # A signed receipt lets /chat use this server's acoustic language detection without trusting the client.
    receipt = speech_receipt(request.app.state.settings.secret_key, store_id.value, text, detected, prob) if detected and text else None
    return {"text": text, "detected_language": detected, "language_probability": prob, "uncertain": uncertain,
            "speech_receipt": receipt, "engine": stt.name}


@router.post("/api/speech/synthesize", dependencies=[Depends(rate_limit("chat"))])
async def synthesize(body: SynthesizeRequest, request: Request):
    tts = request.app.state.tts
    if not tts.available:
        raise HTTPException(503, "Server text-to-speech is not configured.")
    try:
        audio, mime = await run_in_threadpool(partial(tts.synthesize, body.text, language=body.language))
    except SpeechError as exc:
        raise HTTPException(400, str(exc))
    return Response(content=audio, media_type=mime, headers={"Cache-Control": "no-store"})


def _simulator_enabled(request: Request) -> None:
    # The simulator answers unauthenticated callers, so outside development it does not exist unless explicitly enabled.
    if not request.app.state.settings.phone_simulator_enabled:
        raise HTTPException(404, "Not Found")


@router.post("/api/phone/simulator/{store_id}/calls", dependencies=[Depends(_simulator_enabled), Depends(rate_limit("chat"))])
def simulator_start_call(store_id: StorePath, request: Request):
    started = request.app.state.calls.start(store_id, client=client_key(request))
    if started is None:
        raise HTTPException(429, "Too many calls. Please try again later.", headers={"Retry-After": "1800"})
    return simulator.render(started)


@router.post("/api/phone/simulator/calls/{call_id}/turns", dependencies=[Depends(_simulator_enabled), Depends(rate_limit("chat"))])
async def simulator_turn(call_id: CallId, body: PhoneTurnRequest, request: Request):
    inbound = simulator.parse_inbound({"call_id": call_id, **body.model_dump()})
    outbound = await run_in_threadpool(request.app.state.calls.handle, inbound)
    if outbound is None:
        raise HTTPException(404, "Call not found or already ended.")
    return simulator.render(outbound)

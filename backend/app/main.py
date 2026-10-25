"""FastAPI application factory. Run with: uvicorn app.main:build_app --factory"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import db
from .assistant.llm import OllamaClient
from .assistant.service import Assistant
from .config import Settings, get_settings
from .logging_config import configure_logging
from .phone.session import CallManager
from .routers import account, catalog, chat, voice_phone
from .speech.adapters import NotConfiguredSTT, NotConfiguredTTS
from .stores import StoreId

log = logging.getLogger("app")


def _error(status: int, code: str, message: str, headers: dict | None = None, details: list | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body, headers=headers)


def create_app(settings: Settings | None = None, llm: OllamaClient | None | bool = True) -> FastAPI:
    settings = settings or get_settings()
    if llm is True:
        llm = OllamaClient(settings.ollama_url, settings.ollama_model, settings.ollama_timeout_seconds) if settings.llm_enabled else None
    elif llm is False:
        llm = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.init_pools(settings.store_database_urls)
        log.info("API started (llm=%s)", f"ollama:{settings.ollama_model}" if llm else "disabled")
        yield
        db.close_pools()

    app = FastAPI(title="AI Voice Commerce — Customer Service API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.llm = llm
    app.state.assistant = Assistant(llm)
    app.state.calls = CallManager(app.state.assistant)
    app.state.stt = NotConfiguredSTT()
    app.state.tts = NotConfiguredTTS()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Path only: query strings and bodies are never logged.
        log.info("%s %s %s %.0fms id=%s", request.method, request.url.path, response.status_code, (time.perf_counter() - start) * 1000, request_id)
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_req: Request, exc: StarletteHTTPException):
        codes = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 429: "rate_limited", 503: "unavailable"}
        return _error(exc.status_code, codes.get(exc.status_code, "error"), str(exc.detail), headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_req: Request, exc: RequestValidationError):
        # Report which field failed and why, but never echo the submitted value.
        details = [{"field": ".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]), "issue": e["msg"]} for e in exc.errors()]
        return _error(422, "validation_error", "Some of the information sent was invalid.", details=details)

    @app.exception_handler(Exception)
    async def unhandled(_req: Request, exc: Exception):
        log.exception("Unhandled error: %s", type(exc).__name__)
        return _error(500, "internal_error", "Something went wrong on our side. Please try again.")

    @app.get("/api/health", tags=["health"])
    def health():
        dbs = {s.value: db.check_store_db(s) for s in StoreId}
        llm_ok = bool(llm and llm.is_available())
        return {
            "status": "ok" if all(dbs.values()) else "degraded",
            "databases": dbs,
            "llm": {"enabled": llm is not None, "available": llm_ok, "model": settings.ollama_model if llm else None,
                    "mode": "ollama" if llm_ok else "rule-based fallback"},
        }

    app.include_router(catalog.router)
    app.include_router(account.router)
    app.include_router(chat.router)
    app.include_router(voice_phone.router)
    return app


def build_app() -> FastAPI:
    """Entry point for `uvicorn app.main:build_app --factory`."""
    configure_logging()
    return create_app()

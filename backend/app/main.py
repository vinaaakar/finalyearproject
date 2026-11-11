"""FastAPI application factory. Run with: uvicorn app.main:build_app --factory"""

from __future__ import annotations

import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import db
from . import repositories as repo
from .assistant import truth
from . import migrate, worker
from .commerce import CommerceError
from .assistant.llm import OllamaClient
from .assistant.service import Assistant
from .config import Settings, get_settings
from .logging_config import configure_logging
from .notify import EmailSender, build_sender
from .payments.base import get_provider
from .phone.session import CallManager
from .routers import account, addresses, care, cart, catalog, chat, checkout, voice_phone, staff
from .speech.adapters import build_stt, build_tts
from .stores import StoreId

log = logging.getLogger("app")


def _error(status: int, code: str, message: str, headers: dict | None = None, details: list | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body, headers=headers)


# Responses that may carry personal data must never be stored by browsers or shared caches.
_PRIVATE_PATH = re.compile(r"/(auth|me|orders|admin|cart|checkout|chat|payments|speech|phone|addresses)(/|$)")
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


def _security_headers(request: Request, response, settings: Settings) -> None:
    """Headers for every API response. The API serves JSON (and short audio clips), never pages to embed, so the
    policy is maximally strict; the development-only API docs page loads its own scripts and is exempted from CSP.
    Storefront pages are served by Vite (dev) or the web host (production): their headers are documented in
    docs/security.md."""
    h = response.headers
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "no-referrer"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    h["Cross-Origin-Opener-Policy"] = "same-origin"
    if not request.url.path.startswith(_DOCS_PATHS):
        h["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    if settings.app_env == "production":
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.headers.get("authorization") or _PRIVATE_PATH.search(request.url.path):
        h["Cache-Control"] = "no-store"


def create_app(settings: Settings | None = None, llm: OllamaClient | None | bool = True, mailer: EmailSender | None = None) -> FastAPI:
    settings = settings or get_settings()
    if llm is True:
        llm = OllamaClient(settings.ollama_url, settings.ollama_model, settings.ollama_timeout_seconds) if settings.llm_enabled else None
    elif llm is False:
        llm = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.init_pools(settings.store_database_urls)
        # Schema guard (Phase G): this code needs every migration in backend/migrations. Starting against an older
        # schema would fail on the first order query, so refuse to start with a clear instruction instead.
        behind = {}
        for store in StoreId:
            try:
                missing = migrate.pending_versions(settings.store_database_urls[store.value])
            except Exception:  # database not reachable: /api/health reports that; don't block start-up here
                continue
            if missing:
                behind[store.value] = missing
        # India market: prices come only from approved INR price lists (product_prices) — never converted. Products
        # without one are shown as "price not set" and can't be ordered; /api/health reports how complete the list is.
        if behind:
            db.close_pools()
            raise RuntimeError(f"database schema is behind this code: {behind}. Back up (scripts/backup_db.sh), then run "
                               "`python -m app.migrate --plan --backup backups/db-<ts>` and `--apply` (docs/database-safety.md).")
        log.info("API started (llm=%s)", f"ollama:{settings.ollama_model}" if llm else "disabled")
        # Stored policy text that promises services this system doesn't provide. The assistant never repeats these
        # claims (assistant/truth.py), but the text itself needs a reviewed data correction, so make it visible.
        for store in StoreId:
            try:
                found = truth.policy_content_warnings(repo.get_policies(store, "en"))
            except Exception:  # database not reachable yet: health reports that separately
                continue
            app.state.policy_warnings[store.value] = found
            if found:
                log.warning("Policy text for %s mentions unsupported services (%s); the assistant suppresses them. "
                            "Correct the stored policy text with a reviewed data migration.", store.value, "; ".join(found))
        yield
        db.close_pools()

    docs = settings.api_docs_enabled
    app = FastAPI(title="AI Voice Commerce — Customer Service API", version="0.1.0", lifespan=lifespan,
                  docs_url="/docs" if docs else None, redoc_url="/redoc" if docs else None,
                  openapi_url="/openapi.json" if docs else None)
    app.state.settings = settings
    app.state.policy_warnings = {}
    app.state.llm = llm
    app.state.payments = get_provider(settings.payment_provider)
    app.state.assistant = Assistant(llm, payments=app.state.payments, settings=settings)
    app.state.calls = CallManager(app.state.assistant)
    app.state.stt = build_stt(settings.speech_stt, settings.whisper_cpp_bin, settings.whisper_model_path,
                              en_model_path=settings.whisper_en_model_path, languages=settings.speech_languages,
                              default_language=settings.speech_default_language, detect=settings.speech_language_detection)
    app.state.tts = build_tts(settings.speech_tts, settings.tts_voice, {"ta": settings.tts_voice_ta, "hi": settings.tts_voice_hi})
    app.state.mailer = mailer or build_sender(settings.email_delivery, settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Cart-Token", "Idempotency-Key"],
    )

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:  # unhandled errors would otherwise bypass this middleware (and its headers)
            log.exception("Unhandled error: %s", type(exc).__name__)
            response = _error(500, "internal_error", "Something went wrong on our side. Please try again.")
        response.headers["X-Request-ID"] = request_id
        _security_headers(request, response, settings)
        # Path only: query strings and bodies are never logged.
        log.info("%s %s %s %.0fms id=%s", request.method, request.url.path, response.status_code, (time.perf_counter() - start) * 1000, request_id)
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_req: Request, exc: StarletteHTTPException):
        codes = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict", 413: "too_large", 429: "rate_limited", 503: "unavailable"}
        return _error(exc.status_code, codes.get(exc.status_code, "error"), str(exc.detail), headers=getattr(exc, "headers", None))

    @app.exception_handler(CommerceError)
    async def commerce_error(_req: Request, exc: CommerceError):
        return _error(exc.status, exc.code, exc.message, details=exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_req: Request, exc: RequestValidationError):
        # Report which field failed and why, but never echo the submitted value.
        details = [{"field": ".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]), "issue": e["msg"].removeprefix("Value error, ")}
                   for e in exc.errors()]
        return _error(422, "validation_error", "Some of the information sent was invalid.", details=details)

    @app.exception_handler(Exception)
    async def unhandled(_req: Request, exc: Exception):
        log.exception("Unhandled error: %s", type(exc).__name__)
        return _error(500, "internal_error", "Something went wrong on our side. Please try again.")

    @app.get("/api/health/live", tags=["health"])
    def live():
        """Liveness: the process is serving requests (restart the container if this fails)."""
        return {"status": "ok"}

    @app.get("/api/health/ready", tags=["health"])
    def ready():
        """Readiness: both store databases answer. 503 takes the instance out of the load balancer."""
        dbs = {s.value: db.check_store_db(s) for s in StoreId}
        ok = all(dbs.values())
        return JSONResponse(status_code=200 if ok else 503, content={"status": "ready" if ok else "not_ready", "databases": dbs})

    @app.get("/api/health", tags=["health"])
    def health():
        dbs = {s.value: db.check_store_db(s) for s in StoreId}
        llm_ok = bool(llm and llm.is_available())
        return {
            "status": "ok" if all(dbs.values()) else "degraded",
            "databases": dbs,
            "payments": {"provider": app.state.payments.name, "sandbox": app.state.payments.sandbox},
            # Topics whose stored policy text claims services that don't exist (suppressed in answers; text needs correcting).
            "policy_warnings": {k: sorted({w.split(":")[0] for w in v}) for k, v in app.state.policy_warnings.items() if v},
            "selling": {s.value: _selling_health(s) for s in StoreId if dbs[s.value]},
            "llm": {"enabled": llm is not None, "available": llm_ok, "model": settings.ollama_model if llm else None,
                    "mode": "ollama" if llm_ok else "rule-based fallback"},
            # Background worker signals (python -m app.worker): queued / dead side effects and last job runs.
            "background": {s.value: _worker_health(s) for s in StoreId if dbs[s.value]},
        }

    def _selling_health(store: StoreId) -> dict:
        from .pricing import price_list_status, selling_currency
        from .shipping_zones import configured
        try:
            cur = selling_currency(settings.store_markets, store)
            status = price_list_status(store)
            info = status["currencies"].get(cur) or {"approved": status["products"], "complete": True}
            market = settings.store_markets.get(store.value, "US")
            return {"market": market, "currency": cur, "products": status["products"], "priced": info["approved"],
                    "prices_complete": info["complete"], "shipping_configured": configured(store, settings.shipping_config_dir, market)}
        except Exception:
            return {"error": "unavailable"}

    def _worker_health(store: StoreId) -> dict:
        try:
            return worker.health(store)
        except Exception:
            return {"error": "unavailable"}

    app.include_router(catalog.router)
    app.include_router(account.router)
    app.include_router(addresses.router)
    app.include_router(cart.router)
    app.include_router(checkout.router)
    app.include_router(chat.router)
    app.include_router(voice_phone.router)
    app.include_router(staff.router)
    app.include_router(care.router)
    return app


def build_app() -> FastAPI:
    """Entry point for `uvicorn app.main:build_app --factory`."""
    configure_logging()
    return create_app()

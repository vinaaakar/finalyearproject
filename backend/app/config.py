"""Environment-driven settings with validation.

Values come from the process environment, falling back to the project-root `.env`.
Validation errors name the offending variable but never echo its value.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


class ConfigError(RuntimeError):
    pass


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class Settings:
    app_env: str
    # repr=False: secrets and credential-bearing URLs must never appear in logs or test tracebacks.
    secret_key: str = field(repr=False)
    token_ttl_minutes: int
    store_database_urls: dict[str, str] = field(repr=False)
    llm_enabled: bool
    ollama_url: str
    ollama_model: str
    ollama_timeout_seconds: float
    cors_origins: list[str]
    rate_limit_chat_per_min: int
    rate_limit_login_per_min: int
    rate_limit_default_per_min: int
    phone_number_store_map: dict[str, str] = field(default_factory=dict)
    payment_provider: str = "sandbox"
    password_reset_ttl_minutes: int = 30
    email_delivery: str = "dev_outbox"  # dev_outbox | none
    store_public_urls: dict[str, str] = field(default_factory=dict)
    speech_stt: str = "none"            # none | whisper_cpp
    whisper_cpp_bin: str = "whisper-cli"
    whisper_model_path: str = ""
    whisper_en_model_path: str = ""     # optional English-only model used when the language is English
    speech_languages: tuple[str, ...] = ("ta", "en", "hi")
    speech_default_language: str = "ta"  # Tamil by default
    speech_language_detection: bool = True
    speech_tts: str = "none"            # none | macos_say
    tts_voice: str = "Samantha"
    tts_voice_ta: str = "Vani"
    tts_voice_hi: str = "Lekha"
    # The text phone SIMULATOR answers unauthenticated callers (order number + postal code), so it is only
    # reachable in development unless PHONE_SIMULATOR_ENABLED=true is set explicitly.
    phone_simulator_enabled: bool = False
    # Reverse proxies whose X-Forwarded-For header is believed (exact IP addresses). Empty = use the peer address.
    trusted_proxies: tuple[str, ...] = ()
    # Interactive API docs (/docs, /redoc, /openapi.json): development only unless API_DOCS_ENABLED=true.
    api_docs_enabled: bool = False
    # Background worker (Phase G, `python -m app.worker`): unpaid orders hold reserved stock, so the worker cancels
    # them after this long (an operational setting the owner should confirm; docs/business-information.md).
    # Market per store (app/markets.py). This project is India-only: both stores sell in India, in INR, using owner-
    # approved (here: academic demonstration) prices from product_prices — never converted from the USD catalogue.
    # STORE_A_MARKET / STORE_B_MARKET=US keeps the original US behaviour (used by the legacy regression tests).
    store_markets: dict[str, str] = field(default_factory=lambda: {"store-a": "IN", "store-b": "IN"})
    # Phase J: HttpOnly cookie sessions + CSRF double-submit instead of bearer tokens in browser storage.
    auth_cookies: bool = False
    # Country-aware checkout: countries each store's checkout offers, the default for NEW customers (customers with
    # earlier orders default to the country of their last order), and where owner-configured non-US rates live.
    checkout_countries: tuple[str, ...] = ("IN",)
    default_checkout_country: dict[str, str] = field(default_factory=lambda: {"store-a": "IN", "store-b": "IN"})
    shipping_config_dir: Path = field(default=PROJECT_ROOT / "config" / "shipping")
    smtp: Any = field(default=None, repr=False)        # notify.SmtpConfig when EMAIL_DELIVERY=smtp
    log_format: str = "text"                           # text | json
    unpaid_order_ttl_minutes: int = 1440
    worker_max_attempts: int = 10


def load_settings(env: dict[str, str] | None = None, env_file: Path = DEFAULT_ENV_FILE) -> Settings:
    merged = {**_read_env_file(env_file), **(env if env is not None else os.environ)}
    errors: list[str] = []

    def get(name: str, default: str | None = None) -> str:
        value = merged.get(name, default)
        if value is None or value == "":
            errors.append(f"{name} is required")
            return ""
        return value

    def get_int(name: str, default: str, minimum: int = 1) -> int:
        raw = get(name, default)
        try:
            value = int(raw)
        except ValueError:
            errors.append(f"{name} must be an integer")
            return minimum
        if value < minimum:
            errors.append(f"{name} must be >= {minimum}")
        return value

    secret = get("APP_SECRET_KEY")
    if secret and (len(secret) < 32 or secret.startswith("change-me")):
        errors.append("APP_SECRET_KEY must be at least 32 random characters (not the example value)")

    db_urls = {"store-a": get("STORE_A_DATABASE_URL"), "store-b": get("STORE_B_DATABASE_URL")}
    for name, url in (("STORE_A_DATABASE_URL", db_urls["store-a"]), ("STORE_B_DATABASE_URL", db_urls["store-b"])):
        if url and urlparse(url).scheme not in ("postgresql", "postgres"):
            errors.append(f"{name} must be a postgresql:// URL")
    if db_urls["store-a"] and db_urls["store-a"] == db_urls["store-b"]:
        errors.append("STORE_A_DATABASE_URL and STORE_B_DATABASE_URL must point to different databases")
    else:
        parsed = {k: urlparse(v) for k, v in db_urls.items() if v}
        if len(parsed) == 2 and parsed["store-a"].path == parsed["store-b"].path and parsed["store-a"].hostname == parsed["store-b"].hostname:
            errors.append("Store A and Store B must use different database names")

    ollama_url = get("OLLAMA_URL", "http://127.0.0.1:11434")
    if ollama_url and urlparse(ollama_url).scheme not in ("http", "https"):
        errors.append("OLLAMA_URL must be an http(s) URL")

    try:
        timeout = float(get("OLLAMA_TIMEOUT_SECONDS", "45"))
    except ValueError:
        errors.append("OLLAMA_TIMEOUT_SECONDS must be a number")
        timeout = 45.0

    phone_map: dict[str, str] = {}
    for pair in filter(None, (p.strip() for p in merged.get("PHONE_NUMBER_STORE_MAP", "").split(","))):
        number, _, store = pair.partition("=")
        if store not in db_urls:
            errors.append("PHONE_NUMBER_STORE_MAP entries must look like +15550100001=store-a")
        else:
            phone_map[number.strip()] = store

    # Only the sandbox provider exists. A real provider must be implemented, configured and
    # explicitly authorised (PAYMENT_LIVE_AUTHORIZED=true) before it can be selected.
    payment_provider = merged.get("PAYMENT_PROVIDER", "sandbox").strip().lower()
    if payment_provider != "sandbox":
        if merged.get("PAYMENT_LIVE_AUTHORIZED", "").lower() != "true":
            errors.append("PAYMENT_PROVIDER other than 'sandbox' requires PAYMENT_LIVE_AUTHORIZED=true")
        else:
            errors.append("PAYMENT_PROVIDER: no live payment provider is implemented yet; use 'sandbox'")

    app_env = get("APP_ENV", "development")
    email_delivery = merged.get("EMAIL_DELIVERY", "dev_outbox" if app_env == "development" else "none").strip().lower()
    smtp = None
    if email_delivery == "smtp":
        from .notify import SmtpConfig
        host, sender = merged.get("SMTP_HOST", "").strip(), merged.get("SMTP_FROM", "").strip()
        port = merged.get("SMTP_PORT", "587").strip()
        if not host or not sender or not port.isdigit():
            errors.append("EMAIL_DELIVERY=smtp needs SMTP_HOST, SMTP_PORT and SMTP_FROM (and usually SMTP_USERNAME/SMTP_PASSWORD)")
        else:
            smtp = SmtpConfig(host, int(port), merged.get("SMTP_USERNAME", "").strip(), merged.get("SMTP_PASSWORD", ""), sender)
    if email_delivery not in ("dev_outbox", "none", "smtp"):
        errors.append("EMAIL_DELIVERY must be 'dev_outbox' or 'none'")

    public_urls = {
        "store-a": merged.get("STORE_A_PUBLIC_URL", "http://127.0.0.1:5180").rstrip("/"),
        "store-b": merged.get("STORE_B_PUBLIC_URL", "http://127.0.0.1:5181").rstrip("/"),
    }
    for name, url in (("STORE_A_PUBLIC_URL", public_urls["store-a"]), ("STORE_B_PUBLIC_URL", public_urls["store-b"])):
        if urlparse(url).scheme not in ("http", "https"):
            errors.append(f"{name} must be an http(s) URL")

    speech_stt = merged.get("SPEECH_STT", "none").strip().lower()
    if speech_stt not in ("none", "whisper_cpp"):
        errors.append("SPEECH_STT must be 'none' or 'whisper_cpp'")
    # Unset → the verified project copies made by scripts/setup_speech_models.sh, if present (models/ is git-ignored).
    project_models = PROJECT_ROOT / "models" / "whisper"
    whisper_model = merged.get("WHISPER_MODEL_PATH", "").strip() or (
        str(project_models / "ggml-base.bin") if (project_models / "ggml-base.bin").is_file() else "")
    if speech_stt == "whisper_cpp" and not (whisper_model and Path(whisper_model).expanduser().is_file()):
        errors.append("WHISPER_MODEL_PATH must point to an existing ggml model file when SPEECH_STT=whisper_cpp")
    default_country = {s: merged.get(f"{s.upper().replace('-', '_')}_DEFAULT_COUNTRY", "IN").strip().upper() for s in ("store-a", "store-b")}
    for s, c in default_country.items():
        if c not in ("IN", "US"):
            errors.append(f"{s.upper().replace('-', '_')}_DEFAULT_COUNTRY must be IN or US")
    store_markets = {s: merged.get(f"{s.upper().replace('-', '_')}_MARKET", "IN").strip().upper() for s in ("store-a", "store-b")}
    for s, m in store_markets.items():
        if m not in ("US", "IN"):
            errors.append(f"{s.upper().replace('-', '_')}_MARKET must be US or IN")
    whisper_en_model = merged.get("WHISPER_EN_MODEL_PATH", "").strip() or (
        str(project_models / "ggml-base.en.bin") if (project_models / "ggml-base.en.bin").is_file() else "")
    if whisper_en_model and not Path(whisper_en_model).expanduser().is_file():
        errors.append("WHISPER_EN_MODEL_PATH must point to an existing ggml model file")
    speech_languages = tuple(dict.fromkeys(c.strip().lower() for c in merged.get("SPEECH_LANGUAGES", "ta,en,hi").split(",") if c.strip()))
    if not speech_languages or any(c not in ("ta", "en", "hi") for c in speech_languages):
        errors.append("SPEECH_LANGUAGES must be a comma-separated subset of ta,en,hi")
    speech_default_language = merged.get("SPEECH_DEFAULT_LANGUAGE", "ta").strip().lower()
    if speech_default_language not in speech_languages:
        errors.append("SPEECH_DEFAULT_LANGUAGE must be one of SPEECH_LANGUAGES")
    detection = merged.get("SPEECH_LANGUAGE_DETECTION", "auto").strip().lower()
    if detection not in ("auto", "off"):
        errors.append("SPEECH_LANGUAGE_DETECTION must be 'auto' or 'off'")
    speech_tts = merged.get("SPEECH_TTS", "none").strip().lower()
    if speech_tts not in ("none", "macos_say"):
        errors.append("SPEECH_TTS must be 'none' or 'macos_say'")
    tts_voice = merged.get("TTS_VOICE", "Samantha").strip()
    tts_voices = {name: merged.get(name, default).strip() for name, default in
                  (("TTS_VOICE", "Samantha"), ("TTS_VOICE_TA", "Vani"), ("TTS_VOICE_HI", "Lekha"))}
    for name, value in tts_voices.items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z ()\-]{0,39}", value):
            errors.append(f"{name} must be a voice name such as Samantha")
    tts_voice = tts_voices["TTS_VOICE"]

    settings = Settings(
        app_env=app_env,
        secret_key=secret,
        token_ttl_minutes=get_int("TOKEN_TTL_MINUTES", "60"),
        store_database_urls=db_urls,
        llm_enabled=merged.get("LLM_ENABLED", "true").lower() in ("1", "true", "yes"),
        ollama_url=ollama_url.rstrip("/"),
        ollama_model=get("OLLAMA_MODEL", "llama3.2:3b"),
        ollama_timeout_seconds=timeout,
        cors_origins=[o.strip() for o in merged.get("CORS_ORIGINS", "").split(",") if o.strip()],
        rate_limit_chat_per_min=get_int("RATE_LIMIT_CHAT_PER_MIN", "30"),
        rate_limit_login_per_min=get_int("RATE_LIMIT_LOGIN_PER_MIN", "10"),
        rate_limit_default_per_min=get_int("RATE_LIMIT_DEFAULT_PER_MIN", "120"),
        phone_number_store_map=phone_map,
        api_docs_enabled=merged.get("API_DOCS_ENABLED", "true" if app_env == "development" else "false").strip().lower()
        in ("1", "true", "yes"),
        trusted_proxies=tuple(p.strip() for p in merged.get("TRUSTED_PROXIES", "").split(",") if p.strip()),
        phone_simulator_enabled=merged.get("PHONE_SIMULATOR_ENABLED", "true" if app_env == "development" else "false").strip().lower()
        in ("1", "true", "yes"),
        payment_provider=payment_provider,
        password_reset_ttl_minutes=get_int("PASSWORD_RESET_TTL_MINUTES", "30"),
        unpaid_order_ttl_minutes=get_int("UNPAID_ORDER_TTL_MINUTES", "1440", minimum=15),
        store_markets=store_markets,
        # India-only unless a store is explicitly configured for the US market.
        checkout_countries=("IN",) if set(store_markets.values()) == {"IN"} else ("IN", "US"),
        auth_cookies=merged.get("AUTH_COOKIES", "false").strip().lower() == "true",
        default_checkout_country=default_country,
        shipping_config_dir=Path(merged.get("SHIPPING_CONFIG_DIR", "").strip() or PROJECT_ROOT / "config" / "shipping").expanduser(),
        smtp=smtp,
        log_format="json" if merged.get("LOG_FORMAT", "text").strip().lower() == "json" else "text",
        worker_max_attempts=get_int("WORKER_MAX_ATTEMPTS", "10"),
        email_delivery=email_delivery,
        store_public_urls=public_urls,
        speech_stt=speech_stt,
        whisper_cpp_bin=merged.get("WHISPER_CPP_BIN", "whisper-cli").strip() or "whisper-cli",
        whisper_model_path=str(Path(whisper_model).expanduser()) if whisper_model else "",
        whisper_en_model_path=str(Path(whisper_en_model).expanduser()) if whisper_en_model else "",
        speech_languages=speech_languages,
        speech_default_language=speech_default_language,
        speech_language_detection=detection == "auto",
        speech_tts=speech_tts,
        tts_voice=tts_voice,
        tts_voice_ta=tts_voices["TTS_VOICE_TA"],
        tts_voice_hi=tts_voices["TTS_VOICE_HI"],
    )
    if errors:
        raise ConfigError("Invalid configuration:\n  - " + "\n  - ".join(errors))
    return settings


@lru_cache
def get_settings() -> Settings:
    return load_settings()


if __name__ == "__main__":
    # `python -m app.config` — validate the environment and exit non-zero on problems.
    try:
        s = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    print(f"Configuration OK (env={s.app_env}, llm_enabled={s.llm_enabled}, model={s.ollama_model}, payments={s.payment_provider}, stt={s.speech_stt}, tts={s.speech_tts}, voice_default={s.speech_default_language})")

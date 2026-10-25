"""Environment-driven settings with validation.

Values come from the process environment, falling back to the project-root `.env`.
Validation errors name the offending variable but never echo its value.
"""

from __future__ import annotations

import os
import sys
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
    secret_key: str
    token_ttl_minutes: int
    store_database_urls: dict[str, str]
    llm_enabled: bool
    ollama_url: str
    ollama_model: str
    ollama_timeout_seconds: float
    cors_origins: list[str]
    rate_limit_chat_per_min: int
    rate_limit_login_per_min: int
    rate_limit_default_per_min: int
    phone_number_store_map: dict[str, str] = field(default_factory=dict)


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

    settings = Settings(
        app_env=get("APP_ENV", "development"),
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
    print(f"Configuration OK (env={s.app_env}, llm_enabled={s.llm_enabled}, model={s.ollama_model})")

"""Minimal Ollama client. The model only phrases replies from context it is given;
it has no tools, no database access and no ability to choose queries."""

from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    pass


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float):
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self._available: tuple[float, bool] | None = None

    def is_available(self, max_age: float = 30.0) -> bool:
        now = time.monotonic()
        if self._available and now - self._available[0] < max_age:
            return self._available[1]
        ok = False
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=2.0)
            names = {m.get("name") for m in r.json().get("models", [])} if r.status_code == 200 else set()
            ok = self.model in names
        except (httpx.HTTPError, ValueError):
            ok = False
        self._available = (now, ok)
        return ok

    def chat(self, messages: list[dict[str, str]]) -> str:
        try:
            r = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "keep_alive": "15m",
                    "options": {"temperature": 0.2, "num_predict": 220, "num_ctx": 4096},
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
            content = r.json().get("message", {}).get("content", "").strip()
        except (httpx.HTTPError, ValueError) as exc:
            self._available = (time.monotonic(), False)
            log.warning("Ollama request failed: %s", type(exc).__name__)
            raise LLMUnavailable() from exc
        if not content:
            raise LLMUnavailable()
        return content

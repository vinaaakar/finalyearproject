"""Logging setup with a filter that redacts secrets before anything is written."""

from __future__ import annotations

import logging
import re

_PATTERNS = [
    (re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s,'\"]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9_\-\.]{16,}"), r"\1[REDACTED]"),
    (re.compile(r"(?i)((?:password|passwd|secret|token|api[_-]?key)[\"']?\s*[:=]\s*[\"']?)[^\s,'\"&}]+"), r"\1[REDACTED]"),
    (re.compile(r"(postgres(?:ql)?://[^:/\s]+:)[^@\s]+@"), r"\1[REDACTED]@"),
]


def redact(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)

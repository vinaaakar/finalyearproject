"""Outbound email adapters (used for password-reset links).

No real email service is configured. In development, messages are written to
`.run/outbox/` (git-ignored, owner-read-only files) so the reset flow can be tried
locally; nothing is sent over the network. Message bodies are never logged.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import PROJECT_ROOT

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    name: str

    def send(self, store: str, email: Email) -> None: ...


class DevOutboxSender:
    name = "dev_outbox"

    def __init__(self, directory: Path = PROJECT_ROOT / ".run" / "outbox"):
        self.directory = directory

    def send(self, store: str, email: Email) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{time.strftime('%Y%m%d-%H%M%S')}-{store}-{time.monotonic_ns() % 10**6}.txt"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(f"To: {email.to}\nSubject: {email.subject}\n\n{email.body}\n")
        log.info("email written to dev outbox store=%s", store)


class DisabledSender:
    name = "none"

    def send(self, store: str, email: Email) -> None:
        log.warning("email delivery is not configured; message not sent store=%s", store)


class MemorySender:
    """For tests."""

    name = "memory"

    def __init__(self):
        self.sent: list[tuple[str, Email]] = []

    def send(self, store: str, email: Email) -> None:
        self.sent.append((store, email))


def build_sender(kind: str) -> EmailSender:
    return DevOutboxSender() if kind == "dev_outbox" else DisabledSender()

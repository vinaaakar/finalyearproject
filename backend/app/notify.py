"""Outbound email adapters (password-reset links, order-shipped notices via the worker's outbox).

- `dev_outbox` (development default): messages are written to `.run/outbox/` (git-ignored, owner-read-only files);
  nothing is sent over the network.
- `smtp` (production, Phase J): any SMTP relay / transactional provider (Amazon SES, Postmark, Mailgun, a company
  server…) configured by EMAIL_DELIVERY=smtp + SMTP_HOST/PORT/USERNAME/PASSWORD/FROM. Not enabled anywhere until those
  credentials are supplied; STARTTLS (or implicit TLS on port 465) is required, plain-text SMTP is refused.
- `none`: delivery disabled (logged).
Message bodies, recipients and credentials are never logged.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
import time
from email.message import EmailMessage
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


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    sender: str               # "Summit Trail Co. <orders@example.org>" — must be a domain you control (SPF/DKIM/DMARC)
    timeout: float = 15.0


class SmtpSender:
    name = "smtp"

    def __init__(self, config: SmtpConfig, smtp_factory=None):
        self.config = config
        self._factory = smtp_factory

    def send(self, store: str, email: Email) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.config.sender, email.to, email.subject
        msg.set_content(email.body)
        ctx = ssl.create_default_context()
        c = self.config
        if self._factory:
            client = self._factory(c.host, c.port, c.timeout)
        elif c.port == 465:
            client = smtplib.SMTP_SSL(c.host, c.port, timeout=c.timeout, context=ctx)
        else:
            client = smtplib.SMTP(c.host, c.port, timeout=c.timeout)
        with client:
            if c.port != 465:
                client.starttls(context=ctx)          # refuses to continue without TLS (raises if unsupported)
            if c.username:
                client.login(c.username, c.password)
            client.send_message(msg)
        log.info("email sent via smtp store=%s", store)


def build_sender(kind: str, settings=None) -> EmailSender:
    if kind == "dev_outbox":
        return DevOutboxSender()
    if kind == "smtp" and settings is not None and settings.smtp is not None:
        return SmtpSender(settings.smtp)
    return DisabledSender()

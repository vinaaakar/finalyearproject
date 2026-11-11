"""Phase J: production e-mail (SMTP, configurable, TLS required), health probes, JSON logging with redaction."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from app.config import ConfigError, load_settings
from app.logging_config import JsonFormatter, RedactingFilter
from app.notify import DevOutboxSender, DisabledSender, Email, SmtpConfig, SmtpSender, build_sender

BASE = {"APP_ENV": "production", "APP_SECRET_KEY": "x" * 48, "STORE_A_DATABASE_URL": "postgresql://u:p@h/a",
        "STORE_B_DATABASE_URL": "postgresql://u:p@h/b", "CORS_ORIGINS": "https://a.example.org"}


class FakeSMTP:
    def __init__(self, host, port, timeout):
        self.host, self.port, self.calls, self.sent = host, port, [], []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.calls.append("quit")

    def starttls(self, context):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user))

    def send_message(self, msg):
        self.sent.append(msg)


def test_smtp_sender_requires_tls_logs_in_and_sends(caplog):
    made = []
    sender = SmtpSender(SmtpConfig("smtp.example.org", 587, "user", "s3cret-pass", "Summit Trail Co. <orders@example.org>"),
                        smtp_factory=lambda h, p, t: made.append(FakeSMTP(h, p, t)) or made[-1])
    with caplog.at_level(logging.INFO):
        sender.send("store-a", Email(to="pat@example.com", subject="Order SA-50001 has shipped", body="Tracking BD123"))
    smtp = made[0]
    assert smtp.calls[:2] == ["starttls", ("login", "user")]
    msg = smtp.sent[0]
    assert msg["To"] == "pat@example.com" and msg["From"].endswith("<orders@example.org>") and "Tracking BD123" in msg.get_content()
    logged = caplog.text
    assert "pat@example.com" not in logged and "Tracking BD123" not in logged and "s3cret-pass" not in logged


def test_smtp_needs_explicit_configuration():
    with pytest.raises(ConfigError, match="EMAIL_DELIVERY=smtp needs"):
        load_settings(env={**BASE, "EMAIL_DELIVERY": "smtp"}, env_file=Path("/nonexistent"))
    s = load_settings(env={**BASE, "EMAIL_DELIVERY": "smtp", "SMTP_HOST": "smtp.example.org", "SMTP_FROM": "orders@example.org",
                           "SMTP_USERNAME": "u", "SMTP_PASSWORD": "p"}, env_file=Path("/nonexistent"))
    assert isinstance(build_sender(s.email_delivery, s), SmtpSender)
    assert "SMTP_PASSWORD" not in repr(s) and "'p'" not in repr(s)          # credentials never in reprs/tracebacks


def test_development_keeps_the_local_outbox_and_production_defaults_to_disabled():
    dev = load_settings(env={**BASE, "APP_ENV": "development"}, env_file=Path("/nonexistent"))
    assert isinstance(build_sender(dev.email_delivery, dev), DevOutboxSender)
    prod = load_settings(env=BASE, env_file=Path("/nonexistent"))
    assert isinstance(build_sender(prod.email_delivery, prod), DisabledSender)


def test_health_probes(client):
    assert client.get("/api/health/live").json() == {"status": "ok"}
    r = client.get("/api/health/ready")
    assert r.status_code == 200 and r.json()["status"] == "ready"


def test_readiness_fails_when_a_database_is_down(client, monkeypatch):
    from app import db
    monkeypatch.setattr(db, "check_store_db", lambda s: s.value == "store-a")
    r = client.get("/api/health/ready")
    assert r.status_code == 503 and r.json()["databases"] == {"store-a": True, "store-b": False}


def test_json_logs_are_one_object_per_line_and_redacted():
    rec = logging.LogRecord("app", logging.INFO, __file__, 1, "login with password=hunter2 and Bearer abcdefghijklmnopqrstuv", None, None)
    RedactingFilter().filter(rec)
    out = json.loads(JsonFormatter().format(rec))
    assert out["level"] == "INFO" and out["logger"] == "app"
    assert "hunter2" not in out["msg"] and "abcdefghijklmnopqrstuv" not in out["msg"] and "[REDACTED]" in out["msg"]

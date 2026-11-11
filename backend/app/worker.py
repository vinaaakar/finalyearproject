"""Background worker (Phase G; design: docs/scheduler-architecture.md).

    python -m app.worker --once            run every due job and drain the outbox once, then exit (cron-style trigger)
    python -m app.worker                   loop every --interval seconds until SIGTERM / Ctrl-C
    python -m app.worker --store store-a   one store only

Per store database (never mixed):
- Periodic jobs run under a session advisory lock per job, so only one worker instance runs a job at a time; their
  outcome is recorded in `job_runs` (start, success, error, counts, summary).
    expire_unpaid   every 5 min: unpaid orders older than UNPAID_ORDER_TTL_MINUTES are cancelled and their stock released
                    — after asking the payment provider, so a paid-but-unverified order is marked paid instead.
- The `outbox` is drained with `FOR UPDATE SKIP LOCKED` claims and a lease (`locked_until`): two workers never process the
  same row, and a row whose worker died is picked up again when the lease expires. Handlers are idempotent.
  Failure → retry after min(2^attempts, 360) minutes; after WORKER_MAX_ATTEMPTS → `dead` (logged as an error and
  reported by /api/health). Message bodies, e-mail addresses and tokens are never logged.

The worker is NOT started by scripts/start.sh; run it by hand in development. It uses the same per-store database
roles and settings as the API and opens no network port.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import time
import zlib
from dataclasses import dataclass, field
from typing import Callable

from . import commerce, db
from .config import Settings, load_settings
from .notify import Email, EmailSender, build_sender
from .payments.base import PaymentProvider, get_provider
from .repositories import store_connection
from .stores import STORE_BRANDING, StoreId

log = logging.getLogger("app.worker")

LEASE = "2 minutes"
BATCH = 20


def _job_lock_key(job: str) -> int:
    return 0x6176_6300_0000_0000 | zlib.crc32(job.encode())


@dataclass
class Worker:
    settings: Settings
    provider: PaymentProvider
    sender: EmailSender
    stores: list[StoreId]
    intervals: dict[str, int] = field(default_factory=lambda: {"expire_unpaid": 300})
    now: Callable[[], float] = time.time
    stop: bool = False

    # ---- periodic jobs ------------------------------------------------------------------------------------------------
    def run_job(self, store: StoreId, job: str, fn: Callable[[StoreId], dict], *, force: bool = False) -> dict | None:
        """Run `job` for `store` if due (or forced) and no other instance holds its lock. Returns its summary or None."""
        with store_connection(store) as conn:
            if not conn.execute("SELECT pg_try_advisory_lock(%s)", [_job_lock_key(job)]).fetchone()["pg_try_advisory_lock"]:
                log.info("job skipped (running elsewhere) store=%s job=%s", store.value, job)
                return None
            try:
                due = force or conn.execute(
                    "SELECT coalesce(max(last_started_at) < now() - make_interval(secs => %s), true) AS due FROM job_runs WHERE job = %s",
                    [self.intervals.get(job, 300), job]).fetchone()["due"]
                if not due:
                    return None
                conn.execute("INSERT INTO job_runs (job, last_started_at, runs) VALUES (%s, now(), 1) "
                             "ON CONFLICT (job) DO UPDATE SET last_started_at = now(), runs = job_runs.runs + 1", [job])
                conn.commit()
                try:
                    summary = fn(store)
                except Exception as e:   # recorded and logged; the next run retries
                    conn.rollback()
                    conn.execute("UPDATE job_runs SET last_error = %s, last_error_at = now(), failures = failures + 1 WHERE job = %s",
                                 [f"{type(e).__name__}: {str(e)[:300]}", job])
                    conn.commit()
                    log.error("job failed store=%s job=%s error=%s", store.value, job, type(e).__name__)
                    return {"error": type(e).__name__}
                conn.execute("UPDATE job_runs SET last_succeeded_at = now(), last_summary = %s::jsonb WHERE job = %s",
                             [json.dumps(summary), job])
                conn.commit()
                log.info("job ok store=%s job=%s %s", store.value, job, " ".join(f"{k}={v}" for k, v in summary.items()))
                return summary
            finally:
                conn.execute("SELECT pg_advisory_unlock(%s)", [_job_lock_key(job)])
                conn.commit()

    def expire_unpaid(self, store: StoreId) -> dict:
        ttl = self.settings.unpaid_order_ttl_minutes
        with store_connection(store) as conn:
            numbers = [r["order_number"] for r in conn.execute(
                "SELECT order_number FROM orders WHERE status = 'pending_payment' AND placed_at < now() - make_interval(mins => %s) "
                "ORDER BY placed_at LIMIT 200", [ttl]).fetchall()]
        counts = {"expired": 0, "paid": 0, "skipped": 0, "failed": 0}
        for number in numbers:                     # each order in its own short transaction: one failure doesn't stop the rest
            try:
                counts[commerce.expire_unpaid_order(store, number, self.provider, ttl)] += 1
            except Exception as e:
                counts["failed"] += 1
                log.error("expiry failed store=%s error=%s", store.value, type(e).__name__)
        return counts

    # ---- outbox -------------------------------------------------------------------------------------------------------
    def claim(self, store: StoreId, limit: int = BATCH) -> list[dict]:
        with store_connection(store) as conn, conn.transaction():
            return conn.execute(
                f"UPDATE outbox SET locked_until = now() + interval '{LEASE}', attempts = attempts + 1 WHERE id IN ("
                "  SELECT id FROM outbox WHERE status = 'pending' AND available_at <= now() "
                "  AND (locked_until IS NULL OR locked_until < now()) ORDER BY id FOR UPDATE SKIP LOCKED LIMIT %s) "
                "RETURNING id, kind, payload, attempts", [limit]).fetchall()

    def drain(self, store: StoreId) -> dict:
        counts = {"done": 0, "retry": 0, "dead": 0}
        for row in self.claim(store):
            try:
                self.handle(store, row)
            except Exception as e:
                dead = row["attempts"] >= self.settings.worker_max_attempts
                with store_connection(store) as conn, conn.transaction():
                    conn.execute(
                        "UPDATE outbox SET status = CASE WHEN %s THEN 'dead' ELSE status END, locked_until = NULL, last_error = %s, "
                        "available_at = now() + make_interval(mins => least(power(2, attempts)::int, 360)) WHERE id = %s",
                        [dead, f"{type(e).__name__}: {str(e)[:300]}", row["id"]])
                counts["dead" if dead else "retry"] += 1
                (log.error if dead else log.warning)("outbox %s store=%s kind=%s attempt=%d error=%s", "dead" if dead else "retry",
                                                     store.value, row["kind"], row["attempts"], type(e).__name__)
                continue
            with store_connection(store) as conn, conn.transaction():
                conn.execute("UPDATE outbox SET status = 'done', processed_at = now(), locked_until = NULL, last_error = NULL "
                             "WHERE id = %s AND status = 'pending'", [row["id"]])
            counts["done"] += 1
        return counts

    def handle(self, store: StoreId, row: dict) -> None:
        handler = {"email.order_shipped": self._email_order_shipped, "email.care_update": self._email_care_update}.get(row["kind"])
        if handler is None:
            raise ValueError(f"no handler for {row['kind']}")
        handler(store, row["payload"])

    def _email_care_update(self, store: StoreId, payload: dict) -> None:
        """A customer-care request changed (status or a staff message). Composed at send time from current data; internal
        staff notes are never included. Refund requests say plainly that refunds are simulated."""
        from .care_requests import SIMULATED_REFUND_NOTICE, STATUS_LABELS
        with store_connection(store) as conn:
            r = conn.execute("SELECT r.id, r.reference, r.kind, r.status, c.email, c.full_name FROM care_requests r "
                             "JOIN customers c ON c.id = r.customer_id WHERE r.reference = %s", [payload["reference"]]).fetchone()
            if r is None:
                raise LookupError("care request not found")
            last = conn.execute("SELECT body FROM care_request_events WHERE request_id = %s AND visibility = 'customer' "
                                "AND actor_role = 'agent' AND body IS NOT NULL ORDER BY id DESC LIMIT 1", [r["id"]]).fetchone()
        name = STORE_BRANDING[store]["name"]
        url = self.settings.store_public_urls.get(store.value, "").rstrip("/")
        lines = [f"Hello {r['full_name'].split(' ')[0]},", "", f"Your {name} request {r['reference']} has been updated.",
                 f"Status: {STATUS_LABELS[r['status']]}"]
        if last:
            lines += ["", f"Message from the {name} team:", last["body"]]
        if r["kind"] == "refund":
            lines += ["", SIMULATED_REFUND_NOTICE]
        if url:
            lines += ["", f"Details: {url}/support/requests/{r['reference']}"]
        lines += ["", f"— {name}"]
        self.sender.send(store.value, Email(to=r["email"], subject=f"{name}: update on {r['reference']}", body="\n".join(lines)))

    def _email_order_shipped(self, store: StoreId, payload: dict) -> None:
        """Composed at send time from current data (the payload holds only the order number)."""
        with store_connection(store) as conn:
            o = conn.execute(
                "SELECT o.order_number, o.carrier, o.tracking_number, o.tracking_url, o.estimated_delivery, c.email, c.full_name "
                "FROM orders o JOIN customers c ON c.id = o.customer_id WHERE o.order_number = %s", [payload["order_number"]]).fetchone()
        if o is None:
            raise LookupError("order not found")
        name = STORE_BRANDING[store]["name"]
        url = self.settings.store_public_urls.get(store.value, "").rstrip("/")
        lines = [f"Hello {o['full_name'].split(' ')[0]},", "", f"Your {name} order {o['order_number']} has shipped."]
        if o["carrier"] or o["tracking_number"]:
            lines.append(f"Carrier: {o['carrier'] or '—'}   Tracking number: {o['tracking_number'] or '—'}")
        if o["tracking_url"]:
            lines.append(f"Track it: {o['tracking_url']}")
        if o["estimated_delivery"]:
            lines.append(f"Estimated delivery: {o['estimated_delivery']:%d %b %Y}")
        if url:
            lines += ["", f"Order details: {url}/orders/{o['order_number']}"]
        lines += ["", f"— {name}"]
        self.sender.send(store.value, Email(to=o["email"], subject=f"{name}: order {o['order_number']} has shipped", body="\n".join(lines)))

    # ---- loop ---------------------------------------------------------------------------------------------------------
    def tick(self, *, force: bool = False) -> dict:
        out = {}
        for store in self.stores:
            out[store.value] = {"expire_unpaid": self.run_job(store, "expire_unpaid", self.expire_unpaid, force=force),
                                "outbox": self.drain(store)}
        return out

    def loop(self, interval: float) -> None:
        while not self.stop:
            try:
                self.tick()
            except Exception as e:     # e.g. database briefly unreachable: log and keep going
                log.error("worker tick failed error=%s", type(e).__name__)
            slept = 0.0
            while slept < interval and not self.stop:
                time.sleep(0.2)
                slept += 0.2


def health(store: StoreId) -> dict:
    """Read-only worker signals for /api/health."""
    with store_connection(store) as conn:
        ob = conn.execute("SELECT count(*) FILTER (WHERE status = 'pending') AS pending, count(*) FILTER (WHERE status = 'dead') AS dead, "
                          "min(created_at) FILTER (WHERE status = 'pending') AS oldest FROM outbox").fetchone()
        jobs = {r["job"]: {"last_succeeded_at": r["last_succeeded_at"].isoformat() if r["last_succeeded_at"] else None,
                           "last_error_at": r["last_error_at"].isoformat() if r["last_error_at"] else None, "failures": r["failures"]}
                for r in conn.execute("SELECT job, last_succeeded_at, last_error_at, failures FROM job_runs").fetchall()}
    return {"outbox_pending": ob["pending"], "outbox_dead": ob["dead"],
            "outbox_oldest_pending": ob["oldest"].isoformat() if ob["oldest"] else None, "jobs": jobs}


def main(argv: list[str] | None = None) -> int:
    from .logging_config import configure_logging

    ap = argparse.ArgumentParser(prog="python -m app.worker")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--store", choices=["all", *[s.value for s in StoreId]], default="all")
    ap.add_argument("--interval", type=float, default=5.0)
    args = ap.parse_args(argv)
    configure_logging()
    settings = load_settings()
    db.init_pools(settings.store_database_urls)
    stores = list(StoreId) if args.store == "all" else [StoreId(args.store)]
    w = Worker(settings, get_provider(settings.payment_provider), build_sender(settings.email_delivery, settings), stores)

    def _stop(*_):
        w.stop = True
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        if args.once:
            print(json.dumps(w.tick(), default=str))
        else:
            log.info("worker started stores=%s interval=%ss", ",".join(s.value for s in stores), args.interval)
            w.loop(args.interval)
    finally:
        db.close_pools()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

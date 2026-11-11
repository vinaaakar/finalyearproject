"""Phase G: background worker — unpaid-order expiry (provider checked first), outbox with leases/retries/dead state,
job locking and observability. Runs against the *_test databases only."""

from __future__ import annotations

import dataclasses
import json

import psycopg
import pytest

from app import worker as w
from app.notify import MemorySender
from app.payments.base import get_provider
from app.seed import AGENT_PASSWORD
from app.stores import StoreId

from .conftest import ADDRESS_A, AGENT_A, db_exec, idem, login, new_customer, set_stock

LAMP = "lumen-300-headlamp"


@pytest.fixture
def make_worker(client, settings):
    def _make(**overrides):
        s = dataclasses.replace(settings, **overrides) if overrides else settings
        return w.Worker(s, client.app.state.payments, MemorySender(), [StoreId.STORE_A])
    return _make


def _unpaid(client, age_minutes=0, start_payment=False):
    set_stock(client.app.state.settings, "store-a", LAMP, 60)
    headers, _ = new_customer(client, "store-a")
    client.post("/api/stores/store-a/cart/items", json={"slug": LAMP, "quantity": 1}, headers=headers)
    number = client.post("/api/stores/store-a/checkout", headers={**headers, **idem()},
                         json={"shipping": ADDRESS_A, "expected_total_cents": 4595}).json()["order"]["order_number"]
    ref = None
    if start_payment:
        ref = client.post(f"/api/stores/store-a/orders/{number}/payments", headers=headers).json()["payment"]["reference"]
    if age_minutes:
        db_exec(client.app.state.settings, "store-a", "UPDATE orders SET placed_at = now() - make_interval(mins => %s) WHERE order_number = %s",
                [age_minutes, number])
    return headers, number, ref


def _status(client, number):
    return db_exec(client.app.state.settings, "store-a", "SELECT status FROM orders WHERE order_number = %s", [number])[0][0]


def _stock(client):
    return db_exec(client.app.state.settings, "store-a", "SELECT stock_qty FROM products WHERE slug = %s", [LAMP])[0][0]


# ---- unpaid-order expiry ---------------------------------------------------------------------------------------------
def test_old_unpaid_orders_expire_and_release_stock(client, make_worker):
    _, old, _ = _unpaid(client, age_minutes=2000)
    _, fresh, _ = _unpaid(client)
    before = _stock(client)
    summary = make_worker().run_job(StoreId.STORE_A, "expire_unpaid", make_worker().expire_unpaid, force=True)
    assert summary["expired"] >= 1 and summary["failed"] == 0
    assert _status(client, old) == "cancelled" and _status(client, fresh) == "pending_payment"
    assert _stock(client) == before + 1
    hist = db_exec(client.app.state.settings, "store-a", "SELECT h.actor_role, h.note FROM order_status_history h JOIN orders o ON o.id = h.order_id "
                                                         "WHERE o.order_number = %s ORDER BY h.id DESC LIMIT 1", [old])[0]
    assert hist == ("system", "unpaid after 1440 minutes")


def test_expiry_is_idempotent(client, make_worker):
    _, number, _ = _unpaid(client, age_minutes=2000)
    wk = make_worker()
    wk.expire_unpaid(StoreId.STORE_A)
    stock = _stock(client)
    assert wk.expire_unpaid(StoreId.STORE_A)["expired"] == 0       # a second run changes nothing
    assert _stock(client) == stock and _status(client, number) == "cancelled"


def test_paid_but_unverified_order_is_marked_paid_not_cancelled(client, make_worker):
    headers, number, ref = _unpaid(client, age_minutes=2000, start_payment=True)
    client.post(f"/api/stores/store-a/payments/sandbox/{ref}/complete", headers=headers, json={"outcome": "success"})   # never verified
    summary = make_worker().expire_unpaid(StoreId.STORE_A)
    assert summary["paid"] >= 1
    assert _status(client, number) == "processing"


def test_pending_payment_attempt_is_cancelled_with_the_order(client, make_worker):
    _, number, ref = _unpaid(client, age_minutes=2000, start_payment=True)     # customer opened payment but never paid
    make_worker().expire_unpaid(StoreId.STORE_A)
    assert _status(client, number) == "cancelled"
    assert db_exec(client.app.state.settings, "store-a", "SELECT status FROM payments WHERE provider_ref = %s", [ref])[0][0] == "cancelled"


def test_ttl_is_configurable(client, make_worker):
    _, number, _ = _unpaid(client, age_minutes=30)
    make_worker(unpaid_order_ttl_minutes=60).expire_unpaid(StoreId.STORE_A)
    assert _status(client, number) == "pending_payment"
    make_worker(unpaid_order_ttl_minutes=20).expire_unpaid(StoreId.STORE_A)
    assert _status(client, number) == "cancelled"


# ---- periodic job locking and job_runs ---------------------------------------------------------------------------------
def test_job_runs_record_success_and_failure(client, make_worker):
    wk = make_worker()
    wk.run_job(StoreId.STORE_A, "probe_ok", lambda s: {"n": 1}, force=True)
    r = db_exec(client.app.state.settings, "store-a", "SELECT last_succeeded_at IS NOT NULL, last_summary FROM job_runs WHERE job = 'probe_ok'")[0]
    assert r[0] and r[1] == {"n": 1}

    def boom(store):
        raise RuntimeError("database said no")
    assert wk.run_job(StoreId.STORE_A, "probe_bad", boom, force=True) == {"error": "RuntimeError"}
    bad = db_exec(client.app.state.settings, "store-a", "SELECT last_error, failures, last_succeeded_at FROM job_runs WHERE job = 'probe_bad'")[0]
    assert bad[0].startswith("RuntimeError") and bad[1] == 1 and bad[2] is None


def test_job_does_not_run_twice_at_once_or_before_it_is_due(client, make_worker, settings):
    wk = make_worker()
    with psycopg.connect(settings.store_database_urls["store-a"], autocommit=True) as other:
        other.execute("SELECT pg_advisory_lock(%s)", [w._job_lock_key("probe_lock")])
        assert wk.run_job(StoreId.STORE_A, "probe_lock", lambda s: pytest.fail("ran while locked"), force=True) is None
    calls = []
    wk.run_job(StoreId.STORE_A, "probe_due", lambda s: calls.append(1) or {}, force=True)
    wk.run_job(StoreId.STORE_A, "probe_due", lambda s: calls.append(1) or {})        # interval not elapsed
    assert calls == [1]


# ---- outbox ------------------------------------------------------------------------------------------------------------
def _ship(client, number):
    agent = login(client, "store-a", AGENT_A, AGENT_PASSWORD)
    r = client.post(f"/api/stores/store-a/staff/orders/{number}/ship", headers=agent,
                    json={"expected_status": "processing", "carrier": "Blue Dart", "tracking_number": "BD55555", "tracking_url": "https://t.example.org/BD55555"})
    assert r.status_code == 200, r.text


def _paid(client):
    headers, number, ref = _unpaid(client, start_payment=True)
    client.post(f"/api/stores/store-a/payments/sandbox/{ref}/complete", headers=headers, json={"outcome": "success"})
    client.post(f"/api/stores/store-a/orders/{number}/payments/verify", headers=headers)
    return number


def _outbox(client, number):
    return db_exec(client.app.state.settings, "store-a", "SELECT status, attempts, last_error, payload FROM outbox WHERE dedupe_key = %s",
                   [f"order_shipped:{number}"])


def test_shipping_queues_one_email_and_the_worker_sends_it(client, make_worker):
    number = _paid(client)
    _ship(client, number)
    (status, attempts, _, payload), = _outbox(client, number)
    assert status == "pending" and payload == {"order_number": number}        # a reference only: no address or body
    wk = make_worker()
    counts = wk.drain(StoreId.STORE_A)
    assert counts["done"] >= 1
    sent = [e for s, e in wk.sender.sent if number in e.subject]
    assert len(sent) == 1
    assert "BD55555" in sent[0].body and "https://t.example.org/BD55555" in sent[0].body and sent[0].to.endswith("@example.com")
    assert _outbox(client, number)[0][0] == "done"
    wk.drain(StoreId.STORE_A)
    assert len([e for s, e in wk.sender.sent if number in e.subject]) == 1           # never re-sent


def test_failures_retry_with_backoff_then_go_dead(client, make_worker):
    number = _paid(client)
    _ship(client, number)

    class Failing(MemorySender):
        def send(self, store, email):
            raise ConnectionError("smtp unreachable")
    wk = make_worker(worker_max_attempts=2)
    wk.sender = Failing()
    wk.drain(StoreId.STORE_A)
    status, attempts, err, _ = _outbox(client, number)[0]
    assert status == "pending" and attempts == 1 and err.startswith("ConnectionError")
    later = db_exec(client.app.state.settings, "store-a", "SELECT available_at > now() FROM outbox WHERE dedupe_key = %s", [f"order_shipped:{number}"])[0][0]
    assert later                                                         # backed off: not retried immediately
    assert wk.drain(StoreId.STORE_A) == {"done": 0, "retry": 0, "dead": 0}
    assert _outbox(client, number)[0][1] == 1
    db_exec(client.app.state.settings, "store-a", "UPDATE outbox SET available_at = now() WHERE dedupe_key = %s", [f"order_shipped:{number}"])
    wk.drain(StoreId.STORE_A)
    assert _outbox(client, number)[0][0] == "dead"
    h = client.get("/api/health").json()["background"]["store-a"]
    assert h["outbox_dead"] >= 1


def test_two_workers_never_claim_the_same_row_and_leases_expire(client, make_worker, settings):
    number = _paid(client)
    _ship(client, number)
    key = f"order_shipped:{number}"
    db_exec(settings, "store-a", "UPDATE outbox SET status = 'done' WHERE status = 'pending' AND dedupe_key <> %s", [key])
    a, b = make_worker(), make_worker()
    first = a.claim(StoreId.STORE_A)
    assert [r["payload"]["order_number"] for r in first] == [number]
    assert b.claim(StoreId.STORE_A) == []                                  # leased by a
    db_exec(settings, "store-a", "UPDATE outbox SET locked_until = now() - interval '1 second' WHERE dedupe_key = %s", [key])   # a "died"
    again = b.claim(StoreId.STORE_A)
    assert [r["attempts"] for r in again] == [2]                         # reclaimed after the lease


def test_outbox_dedupes_the_same_event(client, settings):
    number = _paid(client)
    _ship(client, number)
    db_exec(settings, "store-a", "INSERT INTO outbox (kind, dedupe_key, payload) VALUES ('email.order_shipped', %s, %s::jsonb) "
                                 "ON CONFLICT (dedupe_key) DO NOTHING", [f"order_shipped:{number}", json.dumps({"order_number": number})])
    assert len(_outbox(client, number)) == 1


def test_unknown_kind_fails_safely(client, make_worker, settings):
    db_exec(settings, "store-a", "UPDATE outbox SET status = 'done' WHERE status = 'pending'")
    db_exec(settings, "store-a", "INSERT INTO outbox (kind, dedupe_key) VALUES ('email.unknown_thing', 'probe-unknown-kind')")
    assert make_worker().drain(StoreId.STORE_A)["retry"] == 1
    assert db_exec(settings, "store-a", "SELECT last_error FROM outbox WHERE dedupe_key = 'probe-unknown-kind'")[0][0].startswith("ValueError")


def test_health_reports_background_state(client):
    h = client.get("/api/health").json()
    assert set(h["background"]) == {"store-a", "store-b"}
    assert {"outbox_pending", "outbox_dead", "jobs"} <= set(h["background"]["store-a"])


def test_worker_cli_once_runs_without_error(settings, monkeypatch):
    monkeypatch.setattr(w, "load_settings", lambda: settings)
    monkeypatch.setattr(w, "build_sender", lambda kind, settings=None: MemorySender())
    assert w.main(["--once", "--store", "store-b"]) == 0

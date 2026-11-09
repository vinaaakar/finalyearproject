"""Phase 1.1 — phone verification guard: tiers, exact time windows (mocked clock), fail-closed memory bound,
and caller identity behind a trusted proxy. No real calls; the simulator runs in-process on the test databases."""

from __future__ import annotations

import pytest

from app.phone import session as ps
from app.phone.base import InboundTurn
from app.phone.session import CallManager, VerificationGuard
from app.stores import StoreId
from tests.conftest import make_client

A = StoreId.STORE_A
WINDOW = ps.GUARD_WINDOW_SECONDS


class FakeClock:
    def __init__(self, t: float = 1_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def guard(clock):
    return VerificationGuard(clock=clock)


def fail(guard, client, order, n=1):
    for _ in range(n):
        guard.record_failure(A, client, order)


# ---- exact window semantics --------------------------------------------------------------------------------
def test_lock_holds_until_exactly_one_window_after_the_last_counted_failure(guard, clock):
    fail(guard, "c1", "SA-10001", ps.MAX_FAILURES_PER_CALLER_ORDER)
    assert guard.verification_blocked(A, "c1", "SA-10001")
    clock.advance(WINDOW - 0.001)
    assert guard.verification_blocked(A, "c1", "SA-10001")          # still inside the window
    clock.advance(0.001)
    assert not guard.verification_blocked(A, "c1", "SA-10001")      # now - t == window: expired


def test_window_slides_one_event_at_a_time(guard, clock):
    key = ("fail-caller-order", A.value, "c1", "SA-10001")
    start = clock.t
    for i in range(ps.MAX_FAILURES_PER_CALLER_ORDER):                # failures at t, t+10m, t+20m
        clock.t = start + 600 * i
        fail(guard, "c1", "SA-10001")
    assert guard.verification_blocked(A, "c1", "SA-10001")
    clock.t = start + WINDOW - 0.001                                 # just before the first failure expires
    assert guard.count(key) == 3 and guard.verification_blocked(A, "c1", "SA-10001")
    clock.t = start + WINDOW                                         # first failure expires: 2 left, unlocked
    assert guard.count(key) == 2 and not guard.verification_blocked(A, "c1", "SA-10001")
    clock.t = start + WINDOW + 600                                   # second expires too
    assert guard.count(key) == 1


def test_window_boundary_is_strict(clock):
    g = VerificationGuard(window=100, clock=clock)
    g.add(("calls", "x"))
    clock.advance(99.999)
    assert g.count(("calls", "x")) == 1
    clock.advance(0.001)
    assert g.count(("calls", "x")) == 0


# ---- tiers ---------------------------------------------------------------------------------------------------
def test_tier1_is_per_caller_and_order(guard):
    fail(guard, "c1", "SA-10001", 3)
    assert guard.verification_blocked(A, "c1", "SA-10001")
    assert not guard.verification_blocked(A, "c1", "SA-10002")     # same caller, other order (tier 2 not reached)
    assert not guard.verification_blocked(A, "c2", "SA-10001")     # other caller, same order (tier 3 not reached)


def test_tier2_stops_one_caller_sweeping_many_orders(guard):
    for i in range(ps.MAX_FAILURES_PER_CALLER):
        fail(guard, "c1", f"SA-1000{i}")
    assert guard.verification_blocked(A, "c1", "SA-99999")
    assert not guard.verification_blocked(A, "c2", "SA-99999")


def test_tier3_stops_distributed_guessing_on_one_order(guard):
    for i in range(ps.MAX_FAILURES_PER_ORDER):
        fail(guard, f"caller-{i}", "SA-10001")
    assert guard.verification_blocked(A, "brand-new-caller", "SA-10001")
    assert not guard.verification_blocked(A, "brand-new-caller", "SA-10002")


def test_malicious_lockout_needs_many_identities(guard):
    # One or a few hostile callers cannot lock a customer out of phone verification.
    for i in range(ps.MAX_FAILURES_PER_ORDER // ps.MAX_FAILURES_PER_CALLER_ORDER):   # 6 callers × 3 = 18 < 20
        fail(guard, f"attacker-{i}", "SA-10001", ps.MAX_FAILURES_PER_CALLER_ORDER)
    assert not guard.verification_blocked(A, "real-customer", "SA-10001")


def test_success_forgives_only_the_callers_own_mistakes(guard):
    fail(guard, "c1", "SA-10001", 2)
    for i in range(10):
        fail(guard, f"other-{i}", "SA-10001")
    guard.record_success(A, "c1", "SA-10001")
    assert guard.count(("fail-caller-order", A.value, "c1", "SA-10001")) == 0
    assert guard.count(("fail-order", A.value, "SA-10001")) == 12     # the shared budget is not reset


def test_stores_are_separate(guard):
    fail(guard, "c1", "SA-10001", 3)
    assert not guard.verification_blocked(StoreId.STORE_B, "c1", "SA-10001")


# ---- memory bound: never forget an active lockout; fail closed -------------------------------------------------
def test_flooding_keys_cannot_evict_an_active_lockout(clock):
    g = VerificationGuard(clock=clock, max_keys=12)
    fail(g, "attacker", "SA-10001", 3)                                # 3 keys; tier-1 key is at its threshold
    for i in range(50):                                               # flood with fresh low-count keys
        g.add(("calls", f"flood-{i}"))
    assert g.verification_blocked(A, "attacker", "SA-10001")


def test_guard_fails_closed_when_only_lockouts_remain(clock):
    g = VerificationGuard(clock=clock, max_keys=6)
    for i in range(6):                                                # 6 keys, every one an active tier-1 lockout
        for _ in range(ps.MAX_FAILURES_PER_CALLER_ORDER):
            g.add(("fail-caller-order", A.value, f"caller-{i}", "SA-1"))
    assert len(g._events) == 6 and not g.saturated
    g.add(("calls", "newcomer"))                                      # no room and nothing evictable
    assert g.saturated and ("calls", "newcomer") not in g._events     # memory did not grow
    assert g.verification_blocked(A, "innocent", "SA-777")            # refuses rather than stops counting
    assert all(g.count(("fail-caller-order", A.value, f"caller-{i}", "SA-1")) == 3 for i in range(6))  # nothing forgotten
    clock.advance(WINDOW)
    assert not g.verification_blocked(A, "innocent", "SA-777") and not g.saturated   # recovers when entries expire


def test_overflow_evicts_only_non_locked_keys(clock):
    g = VerificationGuard(clock=clock, max_keys=5)
    for _ in range(ps.MAX_FAILURES_PER_CALLER_ORDER):
        g.add(("fail-caller-order", A.value, "attacker", "SA-1"))     # locked
    for i in range(4):
        g.add(("calls", f"low-{i}"))                                  # 1 event each, evictable
    g.add(("calls", "one-more"))                                      # forces eviction
    assert g.count(("fail-caller-order", A.value, "attacker", "SA-1")) == 3 and not g.saturated


# ---- calls and sessions (mocked clock) ---------------------------------------------------------------------
class _NoAssistant:
    pass


def test_call_start_limit_resets_after_the_window(clock, client):
    cm = CallManager(client.app.state.assistant, clock=clock)
    starts = [cm.start(A, "c1") is not None for _ in range(ps.MAX_CALLS_PER_CALLER + 1)]
    assert starts == [True] * ps.MAX_CALLS_PER_CALLER + [False]
    clock.advance(WINDOW)
    assert cm.start(A, "c1") is not None


def test_idle_session_expires_after_ttl(clock, client):
    cm = CallManager(client.app.state.assistant, clock=clock)
    cid = cm.start(A, "c1").call_id
    clock.advance(ps.SESSION_TTL_SECONDS)
    assert cm.get(cid) is not None
    clock.advance(1)
    assert cm.get(cid) is None and cm.handle(InboundTurn(call_id=cid, speech="hello")) is None


def test_lockout_end_to_end_with_mocked_time(clock, client):
    cm = CallManager(client.app.state.assistant, clock=clock)
    for _ in range(ps.MAX_FAILURES_PER_CALLER_ORDER):
        cid = cm.start(A, "c1").call_id
        cm.handle(InboundTurn(call_id=cid, speech="track order SA-10001"))
        cm.handle(InboundTurn(call_id=cid, digits="00000"))
    cid = cm.start(A, "c1").call_id
    cm.handle(InboundTurn(call_id=cid, speech="track order SA-10001"))
    assert "can't verify orders by phone" in cm.handle(InboundTurn(call_id=cid, digits="80302")).say
    clock.advance(WINDOW)
    cid = cm.start(A, "c1").call_id
    cm.handle(InboundTurn(call_id=cid, speech="track order SA-10001"))
    assert "SA-10001 is shipped" in cm.handle(InboundTurn(call_id=cid, digits="80302")).say


# ---- caller identity -----------------------------------------------------------------------------------------
def test_forwarded_for_is_ignored_from_untrusted_peers(client):
    # Default settings trust no proxy: a spoofed header must not give a fresh identity.
    for i in range(ps.MAX_FAILURES_PER_CALLER):
        h = {"X-Forwarded-For": f"203.0.113.{i}"}
        cid = client.post("/api/phone/simulator/store-a/calls", headers=h).json()["call_id"]
        client.post(f"/api/phone/simulator/calls/{cid}/turns", json={"speech": f"track order SA-1000{i + 1}"}, headers=h)
        client.post(f"/api/phone/simulator/calls/{cid}/turns", json={"digits": "11111"}, headers=h)
    h = {"X-Forwarded-For": "198.51.100.9"}
    cid = client.post("/api/phone/simulator/store-a/calls", headers=h).json()["call_id"]
    client.post(f"/api/phone/simulator/calls/{cid}/turns", json={"speech": "track order SA-10001"}, headers=h)
    r = client.post(f"/api/phone/simulator/calls/{cid}/turns", json={"digits": "80302"}, headers=h).json()
    assert "can't verify orders by phone" in r["say"]                 # still the same (blocked) caller


def test_callers_behind_a_trusted_proxy_are_separate(settings):
    with make_client(settings, trusted_proxies=("testclient",)) as c:
        bad = {"X-Forwarded-For": "203.0.113.50"}
        for i in range(ps.MAX_FAILURES_PER_CALLER):
            cid = c.post("/api/phone/simulator/store-a/calls", headers=bad).json()["call_id"]
            c.post(f"/api/phone/simulator/calls/{cid}/turns", json={"speech": f"track order SA-1000{i + 1}"}, headers=bad)
            c.post(f"/api/phone/simulator/calls/{cid}/turns", json={"digits": "11111"}, headers=bad)
        good = {"X-Forwarded-For": "198.51.100.10"}                    # different customer behind the same proxy
        cid = c.post("/api/phone/simulator/store-a/calls", headers=good).json()["call_id"]
        c.post(f"/api/phone/simulator/calls/{cid}/turns", json={"speech": "track order SA-10001"}, headers=good)
        assert "SA-10001 is shipped" in c.post(f"/api/phone/simulator/calls/{cid}/turns", json={"digits": "80302"}, headers=good).json()["say"]


@pytest.mark.parametrize("header, expected", [
    ("203.0.113.7", "203.0.113.7"),
    ("198.51.100.1, 203.0.113.7", "203.0.113.7"),       # right-most untrusted hop is the client
    ("203.0.113.7, testclient", "203.0.113.7"),         # trusted hops are skipped
    ("not-an-ip", "testclient"),                         # malformed → proxy's own address
    ("", "testclient"),
])
def test_client_key_resolution(settings, header, expected):
    from starlette.requests import Request

    from app.deps import client_key
    with make_client(settings, trusted_proxies=("testclient",)) as c:
        scope = {"type": "http", "app": c.app, "client": ("testclient", 1), "headers": [(b"x-forwarded-for", header.encode())]}
        assert client_key(Request(scope)) == expected

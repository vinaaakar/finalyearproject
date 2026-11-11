"""Phone call state machine shared by all phone providers.

Callers cannot sign in on the phone, so order information is released only after verifying BOTH the order
number and the order's shipping postal code. That is a weak secret (a postal code), so guessing is limited
ACROSS calls (hanging up and calling again does not reset anything), in three tiers:

  1. per caller AND order    MAX_FAILURES_PER_CALLER_ORDER (3)  — a caller who mistypes is stopped for that order
  2. per caller, any order   MAX_FAILURES_PER_CALLER (5)        — one caller can't sweep many orders
  3. per order, any caller   MAX_FAILURES_PER_ORDER (20)        — many callers (rotating IPs) can't share one order's
                                                                  guess budget; high enough that locking a customer
                                                                  out takes 20 attempts from many identities
  plus a cap on starting new calls per caller (MAX_CALLS_PER_CALLER).

While any tier is active the verification step is refused WITHOUT looking the order up, so the reply never
reveals whether a guess was right (privacy first). A locked order affects ONLY phone verification: the customer
can always sign in on the website. Within one window an order can receive at most 20 guesses in total, i.e.
at most 20 of the ~100,000 possible 5-digit codes (0.02%).

Caller identity is the client address seen by the API, resolved through TRUSTED_PROXIES (see deps.client_key),
so callers behind one reverse proxy are not merged into a single identity. A real telephony provider should key
callers by the verified caller ID it supplies instead.

Limitations (documented, not hidden): counters live in this process's memory, so they reset on an API restart and
are not shared between instances; a production deployment with several instances needs a shared counter store
(e.g. Redis or a database table, which would need a migration). Memory is bounded; if the bound is reached while
every tracked key is an active lockout, the guard fails CLOSED (refuses verification) until entries expire.
"""

from __future__ import annotations

import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .. import repositories as repo
from ..assistant.intent import detect_intent, normalise_order_number
from ..assistant.service import ORDER_PREFIX, Assistant, public_order
from ..stores import StoreId
from .base import InboundTurn, OutboundTurn

MAX_VERIFY_FAILURES = 3              # per call (then the call ends)
GUARD_WINDOW_SECONDS = 30 * 60
MAX_FAILURES_PER_CALLER_ORDER = 3    # tier 1
MAX_FAILURES_PER_CALLER = 5          # tier 2
MAX_FAILURES_PER_ORDER = 20          # tier 3
MAX_CALLS_PER_CALLER = 10            # new calls per caller per window
MAX_GUARD_KEYS = 20_000              # memory bound for the counters
SESSION_TTL_SECONDS = 15 * 60
MAX_SESSIONS = 1000
_GOODBYE = re.compile(r"\b(bye|goodbye|that'?s all|no thanks|nothing else|hang up)\b", re.I)

Clock = Callable[[], float]


class VerificationGuard:
    """Sliding-window counters (an event counts while now - t < window). Time comes from an injectable clock."""

    def __init__(self, window: float = GUARD_WINDOW_SECONDS, clock: Clock = time.monotonic, max_keys: int = MAX_GUARD_KEYS):
        self.window = window
        self.clock = clock
        self.max_keys = max_keys
        self.saturated = False                      # fail-closed flag (see module docstring)
        self._events: dict[tuple[str, ...], list[float]] = {}
        self._lock = threading.Lock()

    # ---- primitives (call with the lock held) ----
    def _recent(self, key: tuple[str, ...], now: float) -> list[float]:
        events = [t for t in self._events.get(key, []) if now - t < self.window]
        if events:
            self._events[key] = events
        else:
            self._events.pop(key, None)
        return events

    @staticmethod
    def _threshold(key: tuple[str, ...]) -> int:
        return {"fail-caller-order": MAX_FAILURES_PER_CALLER_ORDER, "fail-caller": MAX_FAILURES_PER_CALLER,
                "fail-order": MAX_FAILURES_PER_ORDER, "calls": MAX_CALLS_PER_CALLER}[key[0]]

    def _make_room(self, now: float) -> None:
        """Bound memory without ever forgetting an active lockout (forgetting one would let a flood of new keys
        reset an attacker's counters)."""
        for k in list(self._events):
            self._recent(k, now)                    # drop expired keys first
        if len(self._events) < self.max_keys:
            self.saturated = False
            return
        evictable = sorted((k for k, ev in self._events.items() if len(ev) < self._threshold(k)), key=lambda k: self._events[k][-1])
        for k in evictable[: max(1, self.max_keys // 10)]:
            self._events.pop(k, None)
        self.saturated = len(self._events) >= self.max_keys

    # ---- public API ----
    def count(self, key: tuple[str, ...]) -> int:
        with self._lock:
            return len(self._recent(key, self.clock()))

    def add(self, key: tuple[str, ...]) -> None:
        with self._lock:
            now = self.clock()
            if key not in self._events and len(self._events) >= self.max_keys:
                self._make_room(now)
                if self.saturated:
                    return                          # nothing evictable: don't grow; verification fails closed
            self._events[key] = self._recent(key, now) + [now]

    def clear(self, key: tuple[str, ...]) -> None:
        with self._lock:
            self._events.pop(key, None)

    def verification_blocked(self, store: StoreId, client: str, order_number: str) -> bool:
        if self.saturated:
            with self._lock:
                self._make_room(self.clock())
            if self.saturated:
                return True
        n = order_number.upper()
        return (self.count(("fail-caller-order", store.value, client, n)) >= MAX_FAILURES_PER_CALLER_ORDER
                or self.count(("fail-caller", store.value, client)) >= MAX_FAILURES_PER_CALLER
                or self.count(("fail-order", store.value, n)) >= MAX_FAILURES_PER_ORDER)

    def record_failure(self, store: StoreId, client: str, order_number: str) -> None:
        n = order_number.upper()
        self.add(("fail-caller-order", store.value, client, n))
        self.add(("fail-caller", store.value, client))
        self.add(("fail-order", store.value, n))

    def record_success(self, store: StoreId, client: str, order_number: str) -> None:
        # A verified caller's own mistakes for this order are forgiven; the shared per-order budget is not.
        self.clear(("fail-caller-order", store.value, client, order_number.upper()))

    def allow_new_call(self, client: str) -> bool:
        key = ("calls", client)
        if self.count(key) >= MAX_CALLS_PER_CALLER:
            return False
        self.add(key)
        return True


LOCKED_SAY = ("I'm sorry, I can't verify orders by phone right now. Please sign in on our website to see your orders, "
              "or contact our support team by email. Goodbye.")


@dataclass
class CallSession:
    call_id: str
    store: StoreId
    client: str = "unknown"
    state: str = "main"  # main | await_order_number | await_postal | ended
    pending_order_number: str | None = None
    verify_failures: int = 0
    last_seen: float = 0.0


class CallManager:
    def __init__(self, assistant: Assistant, clock: Clock = time.monotonic):
        self.assistant = assistant
        self.clock = clock
        self._sessions: dict[str, CallSession] = {}
        self._lock = threading.Lock()
        self.guard = VerificationGuard(clock=clock)

    def start(self, store: StoreId, client: str = "unknown") -> OutboundTurn | None:
        """None when this caller has started too many calls recently (the router answers 429)."""
        if not self.guard.allow_new_call(client):
            return None
        with self._lock:
            self._evict()
            call_id = secrets.token_urlsafe(12)
            self._sessions[call_id] = CallSession(call_id=call_id, store=store, client=client, last_seen=self.clock())
        name = (repo.get_store_profile(store) or {}).get("name", "our store")
        return OutboundTurn(call_id, f"Thanks for calling {name}. I can help with products, shipping, returns, or your order status. How can I help you today?")

    def get(self, call_id: str) -> CallSession | None:
        with self._lock:
            s = self._sessions.get(call_id)
            if s and self.clock() - s.last_seen > SESSION_TTL_SECONDS:
                del self._sessions[call_id]
                return None
            return s

    def handle(self, turn: InboundTurn) -> OutboundTurn | None:
        s = self.get(turn.call_id)
        if s is None or s.state == "ended":
            return None
        s.last_seen = self.clock()
        text = (turn.speech or "").strip()
        digits = (turn.digits or "").strip()

        if text and _GOODBYE.search(text):
            return self._end(s, "Thank you for calling. Goodbye!")

        if s.state == "await_order_number":
            number = normalise_order_number(text) or self._number_from_digits(s.store, digits or re.sub(r"\D", "", text))
            if not number:
                return OutboundTurn(s.call_id, f"Sorry, I didn't catch that. Please say or key in your order number. It starts with {ORDER_PREFIX[s.store]}")
            s.pending_order_number, s.state = number, "await_postal"
            return OutboundTurn(s.call_id, "Thanks. " + self._postal_prompt(s.store))

        if s.state == "await_postal":
            number = s.pending_order_number or ""
            # Refuse before any lookup while a cross-call limit is active, so the answer can't confirm a guess.
            if self.guard.verification_blocked(s.store, s.client, number):
                return self._end(s, LOCKED_SAY)
            postal = re.sub(r"\D", "", digits or text)[:10]
            order = repo.verify_order_for_phone(s.store, number, postal) if postal else None
            if order is None:
                self.guard.record_failure(s.store, s.client, number)
                s.verify_failures += 1
                if s.verify_failures >= MAX_VERIFY_FAILURES:
                    return self._end(s, "I'm sorry, I wasn't able to verify that order. Please contact our support team by email for help. Goodbye.")
                s.state = "await_order_number"
                return OutboundTurn(s.call_id, f"That order number and {self._postal_name(s.store)} don't match our records. "
                                                "Let's try again. Please say or key in your order number.")
            self.guard.record_success(s.store, s.client, number)
            s.state, s.pending_order_number = "main", None
            o = public_order(order)
            msg = f"Order {o['order_number']} is {o['status_label']}."
            if o["estimated_delivery"] and o["status"] in ("processing", "shipped", "out_for_delivery"):
                msg += f" It's expected by {o['estimated_delivery']}."
            return OutboundTurn(s.call_id, msg + " Is there anything else I can help with?")

        # main state
        if not text:
            return OutboundTurn(s.call_id, "How can I help you today?")
        intent = detect_intent(text)
        if "contact" in intent.intents and any(w in text.lower() for w in ("human", "agent", "person", "representative")):
            s.state = "ended"
            return OutboundTurn(s.call_id, "Let me transfer you to a member of our team.", expect_input=False, transfer_to_agent=True)
        if "order_status" in intent.intents:
            if intent.order_number:
                s.pending_order_number, s.state = intent.order_number, "await_postal"
                return OutboundTurn(s.call_id, "Sure. " + self._postal_prompt(s.store))
            s.state = "await_order_number"
            return OutboundTurn(s.call_id, f"Sure. Please say or key in your order number. It starts with {ORDER_PREFIX[s.store]}")
        # The phone simulator is English-only for now.
        result = self.assistant.answer(s.store, text, principal=None, conversation_language="en")
        return OutboundTurn(s.call_id, result.reply)

    # The wording follows the store's market, never the order (looking the order up before verification would reveal
    # whether it exists). India stores ask for the six-digit PIN code; orders placed before the India launch were US
    # orders, so their ZIP code is still accepted and named. A US-market store keeps the original ZIP wording.
    def _india(self, store: StoreId) -> bool:
        view = getattr(self.assistant, "view", None)
        return bool(view is not None and view.market(store) == "IN")

    def _postal_name(self, store: StoreId) -> str:
        return "PIN code" if self._india(store) else "ZIP code"

    def _postal_prompt(self, store: StoreId) -> str:
        if self._india(store):
            return ("To verify it's you, please say or key in the six-digit shipping PIN code for that order. "
                    "For an older order with a US address, use its five-digit ZIP code.")
        return "To verify it's you, please say or key in the five-digit shipping ZIP code for that order."

    def _end(self, s: CallSession, say: str) -> OutboundTurn:
        s.state = "ended"
        return OutboundTurn(s.call_id, say, expect_input=False, hang_up=True)

    @staticmethod
    def _number_from_digits(store: StoreId, digits: str) -> str | None:
        return f"{ORDER_PREFIX[store]}{digits}" if re.fullmatch(r"\d{5}", digits or "") else None

    def _evict(self) -> None:
        now = self.clock()
        for cid in [c for c, s in self._sessions.items() if now - s.last_seen > SESSION_TTL_SECONDS or s.state == "ended"]:
            del self._sessions[cid]
        while len(self._sessions) >= MAX_SESSIONS:
            self._sessions.pop(next(iter(self._sessions)))

"""Phone call state machine shared by all phone providers.

Callers cannot sign in on the phone, so order information is released only after
verifying BOTH the order number and the order's shipping postal code, with a cap
on failed attempts per call.
"""

from __future__ import annotations

import re
import secrets
import threading
import time
from dataclasses import dataclass, field

from .. import repositories as repo
from ..assistant.intent import detect_intent, normalise_order_number
from ..assistant.service import ORDER_PREFIX, Assistant, public_order
from ..stores import StoreId
from .base import InboundTurn, OutboundTurn

MAX_VERIFY_FAILURES = 3
SESSION_TTL_SECONDS = 15 * 60
MAX_SESSIONS = 1000
_GOODBYE = re.compile(r"\b(bye|goodbye|that'?s all|no thanks|nothing else|hang up)\b", re.I)


@dataclass
class CallSession:
    call_id: str
    store: StoreId
    state: str = "main"  # main | await_order_number | await_postal | ended
    pending_order_number: str | None = None
    verify_failures: int = 0
    last_seen: float = field(default_factory=time.monotonic)


class CallManager:
    def __init__(self, assistant: Assistant):
        self.assistant = assistant
        self._sessions: dict[str, CallSession] = {}
        self._lock = threading.Lock()

    def start(self, store: StoreId) -> OutboundTurn:
        with self._lock:
            self._evict()
            call_id = secrets.token_urlsafe(12)
            self._sessions[call_id] = CallSession(call_id=call_id, store=store)
        name = (repo.get_store_profile(store) or {}).get("name", "our store")
        return OutboundTurn(call_id, f"Thanks for calling {name}. I can help with products, shipping, returns, or your order status. How can I help you today?")

    def get(self, call_id: str) -> CallSession | None:
        with self._lock:
            s = self._sessions.get(call_id)
            if s and time.monotonic() - s.last_seen > SESSION_TTL_SECONDS:
                del self._sessions[call_id]
                return None
            return s

    def handle(self, turn: InboundTurn) -> OutboundTurn | None:
        s = self.get(turn.call_id)
        if s is None or s.state == "ended":
            return None
        s.last_seen = time.monotonic()
        text = (turn.speech or "").strip()
        digits = (turn.digits or "").strip()

        if text and _GOODBYE.search(text):
            return self._end(s, "Thank you for calling. Goodbye!")

        if s.state == "await_order_number":
            number = normalise_order_number(text) or self._number_from_digits(s.store, digits or re.sub(r"\D", "", text))
            if not number:
                return OutboundTurn(s.call_id, f"Sorry, I didn't catch that. Please say or key in your order number. It starts with {ORDER_PREFIX[s.store]}")
            s.pending_order_number, s.state = number, "await_postal"
            return OutboundTurn(s.call_id, "Thanks. To verify it's you, please say or key in the five-digit shipping ZIP code for that order.")

        if s.state == "await_postal":
            postal = re.sub(r"\D", "", digits or text)[:10]
            order = repo.verify_order_for_phone(s.store, s.pending_order_number or "", postal) if postal else None
            if order is None:
                s.verify_failures += 1
                if s.verify_failures >= MAX_VERIFY_FAILURES:
                    return self._end(s, "I'm sorry, I wasn't able to verify that order. Please contact our support team by email for help. Goodbye.")
                s.state = "await_order_number"
                return OutboundTurn(s.call_id, "That order number and ZIP code don't match our records. Let's try again. Please say or key in your order number.")
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
                return OutboundTurn(s.call_id, "Sure. To verify it's you, please say or key in the five-digit shipping ZIP code for that order.")
            s.state = "await_order_number"
            return OutboundTurn(s.call_id, f"Sure. Please say or key in your order number. It starts with {ORDER_PREFIX[s.store]}")
        # The phone simulator is English-only for now.
        result = self.assistant.answer(s.store, text, principal=None, conversation_language="en")
        return OutboundTurn(s.call_id, result.reply)

    def _end(self, s: CallSession, say: str) -> OutboundTurn:
        s.state = "ended"
        return OutboundTurn(s.call_id, say, expect_input=False, hang_up=True)

    @staticmethod
    def _number_from_digits(store: StoreId, digits: str) -> str | None:
        return f"{ORDER_PREFIX[store]}{digits}" if re.fullmatch(r"\d{5}", digits or "") else None

    def _evict(self) -> None:
        now = time.monotonic()
        for cid in [c for c, s in self._sessions.items() if now - s.last_seen > SESSION_TTL_SECONDS or s.state == "ended"]:
            del self._sessions[cid]
        while len(self._sessions) >= MAX_SESSIONS:
            self._sessions.pop(next(iter(self._sessions)))

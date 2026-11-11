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
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable

from .. import care_requests as care
from .. import repositories as repo
from ..assistant import i18n
from ..assistant.care_flow import _CANCEL, _NO, _NO as _NO_ORDER, _YES, CATEGORY_NAMES, KIND_NAMES
from ..assistant.care_flow import _reason, _status_name, infer_category
from ..assistant.care_flow import detect as care_detect
from ..assistant.intent import detect_intent, normalise_order_number, sensitive_kind
from ..assistant.language import identify
from ..assistant.service import ORDER_PREFIX, Assistant, public_order
from ..commerce import CommerceError
from ..stores import STORE_BRANDING, StoreId
from .base import InboundTurn, OutboundTurn
from .phone_text import LANGS, LANGUAGE_WORDS, P, p, spelled, spoken_date

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


# ---- the call --------------------------------------------------------------------------------------------------------------
LOCKED_SAY = P["locked"]["en"]
MAX_SILENCES = 3                     # consecutive empty turns before the call ends
MAX_MISSES = 3                       # consecutive not-understood answers to one question before going back to the menu

# Ending the call. Tamil/Hindi have no \b word boundaries (vowel signs are not \w), so those phrases are matched as plain text.
_GOODBYE = re.compile(r"\b(bye|goodbye|good bye|that'?s all|no thanks|nothing else|hang up)\b|போதும்|வேறு எதுவும் (இல்லை|வேண்டாம்)|அவ்வளவுதான்|"
                      r"பை பை|बस इतना ही|और कुछ नहीं|अलविदा|फ़ोन रख|फोन रख|बाय", re.I)
_THANKS_ONLY = re.compile(r"^\s*(ok(ay)?,? )?(thank you( very much| so much)?|thanks( a lot)?|நன்றி|மிக்க நன்றி|ரொம்ப நன்றி|धन्यवाद|"
                          r"बहुत धन्यवाद|शुक्रिया|थैंक यू)[\s.!।]*$", re.I)
# A bare "no" answering "anything else?" ends the call (only in the main menu).
_NO_ONLY = re.compile(r"^\s*(no|nope|no,? that'?s it|இல்லை|வேண்டாம்|नहीं|जी नहीं)[\s.!।]*$", re.I)
# Words for a person, beyond the chat's phrasing: "operator", "agent", "representative", and the "team" the menu offers.
_PHONE_HUMAN = re.compile(r"\b(operator|agent|representative|customer (care|service)|someone|team|staff)\b|ஆபரேட்டர்|குழு|ஊழியர்|"
                          r"ऑपरेटर|टीम|किसी से बात", re.I)
_RESTART = re.compile(r"\b(start (again|over)|main menu|menu|go back|cancel)\b|ரத்து|மீண்டும் தொடங்கு|मेनू|रद्द|शुरू से", re.I)
_DIGIT_WORDS = {
    "zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
    "nine": "9",
    "பூஜ்ஜியம்": "0", "சுழியம்": "0", "ஒன்று": "1", "ஒண்ணு": "1", "இரண்டு": "2", "ரெண்டு": "2", "மூன்று": "3", "மூணு": "3",
    "நான்கு": "4", "நாலு": "4", "ஐந்து": "5", "அஞ்சு": "5", "ஆறு": "6", "ஏழு": "7", "எட்டு": "8", "ஒன்பது": "9",
    "शून्य": "0", "ज़ीरो": "0", "जीरो": "0", "एक": "1", "दो": "2", "तीन": "3", "चार": "4", "पांच": "5", "पाँच": "5", "छह": "6",
    "छः": "6", "छे": "6", "सात": "7", "आठ": "8", "नौ": "9",
}


# Ordinals only (never the bare number words: "the second one" must not pick item 1 because of "one").
_ORDINALS = [r"\b(first|1st)\b|முதல்|पहला|पहले|पहली", r"\b(second|2nd)\b|இரண்டாவது|दूसरा|दूसरी", r"\b(third|3rd)\b|மூன்றாவது|तीसरा|तीसरी",
             r"\b(fourth|4th)\b|நான்காவது|चौथा|चौथी", r"\b(fifth|5th)\b|ஐந்தாவது|पाँचवाँ|पांचवां|पाँचवीं",
             r"\b(sixth|6th)\b|ஆறாவது|छठा|छठी", r"\b(seventh|7th)\b|ஏழாவது|सातवाँ|सातवीं"]


def ascii_digits(text: str) -> str:
    """Tamil (௧…) and Devanagari (१…) numerals → 0-9, so a transcript in any script verifies against the database."""
    return "".join(str(unicodedata.digit(ch)) if ch.isdigit() else ch for ch in text or "")


_CODE_FILLER = {"it's", "its", "it", "is", "my", "the", "pin", "code", "zip", "number", "order", "pincode", "uh", "um", "er", "ok",
                "okay", "yes", "sa", "bb", "என்", "எண்", "பின்", "கோட்", "பின்கோட்", "मेरा", "पिन", "कोड", "नंबर", "है",
                # spoken letters of the prefix (S A / B B) in Tamil and Hindi script
                "எஸ்", "ஏ", "பி", "பீ", "एस", "ए", "बी"}


def code_digits(text: str) -> str:
    """Digits of an answer that is ONLY a number ("8 0 3 0 2", "it's eight zero three zero two"). A sentence that merely
    contains a number ("a backpack under 3000 rupees") is not a code, so it never counts as a wrong guess."""
    for tok in re.split(r"[\s,.\-–—/!?।]+", ascii_digits(text).lower()):
        # Single letters are a spelled prefix ("S A one zero zero zero one").
        if tok and len(tok) > 1 and not tok.isdigit() and tok not in _DIGIT_WORDS and tok not in _CODE_FILLER:
            return ""
    return spoken_digits(text)


def spoken_digits(text: str) -> str:
    """All digits in an utterance, including digit words ("eight zero three", "எட்டு பூஜ்ஜியம்", "आठ शून्य")."""
    out = []
    for tok in re.split(r"[\s,.\-–—/]+", ascii_digits(text).lower()):
        if tok.isdigit():
            out.append(tok)
        elif tok in _DIGIT_WORDS:
            out.append(_DIGIT_WORDS[tok])
    return "".join(out)


@dataclass
class CallSession:
    call_id: str
    store: StoreId
    client: str = "unknown"
    # main | await_order_number | await_postal | care_offer | care_item | care_category | care_description | care_confirm | ended
    state: str = "main"
    lang: str = "ta"
    pending_order_number: str | None = None
    verify_failures: int = 0
    last_seen: float = 0.0
    # The one order this caller proved (order number + its shipping postal code). Everything private in the call is limited
    # to this order: a postal code is a weak secret, so the caller never hears about the customer's OTHER orders or requests.
    verified_order: str | None = None
    verified_customer_id: int | None = None
    purpose: str | None = None       # what to do once verified: "status" | "care" | "care_status"
    care: dict[str, Any] | None = None
    silences: int = 0
    misses: int = 0


class CallManager:
    def __init__(self, assistant: Assistant, clock: Clock = time.monotonic):
        self.assistant = assistant
        self.clock = clock
        self._sessions: dict[str, CallSession] = {}
        self._lock = threading.Lock()
        self.guard = VerificationGuard(clock=clock)

    def start(self, store: StoreId, client: str = "unknown", language: str = "ta") -> OutboundTurn | None:
        """None when this caller has started too many calls recently (the router answers 429)."""
        if not self.guard.allow_new_call(client):
            return None
        lang = language if language in LANGS else "ta"
        with self._lock:
            self._evict()
            call_id = secrets.token_urlsafe(12)
            self._sessions[call_id] = CallSession(call_id=call_id, store=store, client=client, lang=lang, last_seen=self.clock())
        say = p(lang, "greeting", store=self._store_name(store), assistant=STORE_BRANDING[store]["assistant_name"]) + p(lang, "other_languages")
        return OutboundTurn(call_id, say, language=lang)

    def get(self, call_id: str) -> CallSession | None:
        with self._lock:
            s = self._sessions.get(call_id)
            if s and self.clock() - s.last_seen > SESSION_TTL_SECONDS:
                del self._sessions[call_id]
                return None
            return s

    # ---- one caller turn ---------------------------------------------------------------------------------------------
    def handle(self, turn: InboundTurn) -> OutboundTurn | None:
        s = self.get(turn.call_id)
        if s is None or s.state == "ended":
            return None
        s.last_seen = self.clock()
        text = ascii_digits((turn.speech or "").strip())
        digits = (turn.digits or "").strip()

        # Silence (no speech recognised, no key pressed) is never a wrong answer: ask again, and end politely after a few.
        if not text and not digits:
            s.silences += 1
            if s.silences >= MAX_SILENCES:
                return self._end(s, p(s.lang, "silence_end"))
            return self._say(s, p(s.lang, "silence") + " " + self._current_question(s))
        s.silences = 0

        if text:
            switched = self._explicit_language(text)
            if switched:
                s.lang = switched
                return self._say(s, p(s.lang, "language_switched") + " " + self._current_question(s))
            found = identify(text)
            if found.status == "detected" and found.language in LANGS:
                s.lang = found.language

        describing = s.state == "care_description"     # the caller's own words: never parsed as a command
        if text and not describing:
            if _GOODBYE.search(text) or _THANKS_ONLY.search(text) or (s.state == "main" and _NO_ONLY.search(text)):
                return self._end(s, p(s.lang, "goodbye", store=self._store_name(s.store)))
            if s.state != "main" and _RESTART.search(text) and not spoken_digits(text):
                cancelled = s.care is not None
                self._reset(s)
                return self._say(s, p(s.lang, "cancelled" if cancelled else "back_to_menu") + " " + p(s.lang, "how_help"))

        handler = {
            "await_order_number": self._on_order_number, "await_postal": self._on_postal, "care_item": self._on_item,
            "care_category": self._on_category, "care_offer": self._on_offer, "care_description": self._on_description, "care_confirm": self._on_confirm,
        }.get(s.state, self._on_main)
        return handler(s, text, digits)

    # ---- main menu ---------------------------------------------------------------------------------------------------
    def _on_main(self, s: CallSession, text: str, digits: str) -> OutboundTurn:
        if not text or _YES.fullmatch(text):        # "yes" to "anything else?": ask what
            return self._say(s, p(s.lang, "how_help"))
        found = care_detect(text)
        if found is None and _PHONE_HUMAN.search(text):
            found = {"kind": "escalation"}
        named = normalise_order_number(text)
        if found and found.get("status"):
            return self._need_order(s, "care_status", named, care_kind=found.get("kind"), reference=found.get("reference"))
        if found and found.get("kind"):
            return self._start_care(s, found["kind"], text, named)
        if "order_status" in detect_intent(text).intents:
            return self._need_order(s, "status", named)
        result = self.assistant.answer(s.store, text, principal=None, conversation_language=s.lang)
        if result.language in LANGS:
            s.lang = result.language
        return self._say(s, result.reply)

    def _need_order(self, s: CallSession, purpose: str, named: str | None, lead: str = "", **extra) -> OutboundTurn:
        """Continue with `purpose` once an order is verified: reuse this call's verified order, or ask for one."""
        s.purpose, s.misses = purpose, 0
        if purpose == "care_status":
            s.care = {"status_kind": extra.get("care_kind"), "reference": extra.get("reference")}
        if s.verified_order and named in (None, s.verified_order):
            return self._after_verified(s, lead)
        if named:
            s.pending_order_number, s.state = named, "await_postal"
            return self._say(s, (lead or p(s.lang, "sure")) + " " + self._postal_prompt(s))
        s.state = "await_order_number"
        ask = p(s.lang, "ask_order_care" if purpose == "care" else "ask_order", prefix=self._prefix(s))
        if purpose == "care" and s.care and s.care["kind"] in ("complaint", "escalation"):
            ask += p(s.lang, "ask_order_no_order")
        return self._say(s, ((lead or p(s.lang, "sure")) + " " + ask).strip())

    # ---- verification ------------------------------------------------------------------------------------------------
    def _on_order_number(self, s: CallSession, text: str, digits: str) -> OutboundTurn:
        number = normalise_order_number(text) or self._number_from_digits(s.store, digits or code_digits(text))
        if number:
            s.pending_order_number, s.state, s.misses = number, "await_postal", 0
            return self._say(s, p(s.lang, "thanks") + " " + self._postal_prompt(s))
        if s.purpose == "care" and s.care and s.care["kind"] in ("complaint", "escalation") and _NO_ORDER.search(text or ""):
            # Without an order there is nothing to verify the caller against, so nothing can be recorded on an account.
            self._reset(s)
            return self._say(s, self._contact_line(s) + " " + p(s.lang, "anything_else"))
        redirect = self._new_request(s, text)
        if redirect:
            return redirect
        return self._missed(s, p(s.lang, "order_not_caught"))

    def _on_postal(self, s: CallSession, text: str, digits: str) -> OutboundTurn:
        number = s.pending_order_number or ""
        other = normalise_order_number(text)
        if other and other != number:                # the caller gave a (different) order number instead
            s.pending_order_number = other
            return self._say(s, p(s.lang, "thanks") + " " + self._postal_prompt(s))
        postal = (digits and re.sub(r"\D", "", digits)) or code_digits(text)
        if not postal:
            redirect = self._new_request(s, text)
            if redirect:
                return redirect
            return self._missed(s, p(s.lang, "pin_not_caught"))
        postal = postal[:10]
        # Refuse before any lookup while a cross-call limit is active, so the answer can't confirm a guess.
        if self.guard.verification_blocked(s.store, s.client, number):
            return self._end(s, p(s.lang, "locked"))
        order = repo.verify_order_for_phone(s.store, number, postal)
        if order is None:
            self.guard.record_failure(s.store, s.client, number)
            s.verify_failures += 1
            if s.verify_failures >= MAX_VERIFY_FAILURES:
                return self._end(s, p(s.lang, "verify_failed_end", email=self._profile(s.store).get("support_email", "")))
            s.state, s.misses = "await_order_number", 0
            return self._say(s, p(s.lang, "no_match_pin" if self._india(s.store) else "no_match_zip") + " "
                             + p(s.lang, "ask_order", prefix=self._prefix(s)))
        self.guard.record_success(s.store, s.client, number)
        s.verified_order, s.verified_customer_id = order["order_number"], order["customer_id"]
        s.pending_order_number, s.misses = None, 0
        return self._after_verified(s, p(s.lang, "thanks"), order)

    def _after_verified(self, s: CallSession, lead: str = "", order: dict[str, Any] | None = None) -> OutboundTurn:
        purpose, s.purpose, s.state = s.purpose, None, "main"
        if purpose == "care" and s.care:
            return self._care_next(s, lead)
        if purpose == "care_status":
            return self._care_status(s)
        order = order or repo.get_order_for_customer(s.store, s.verified_order, s.verified_customer_id)
        if order is None:                           # cannot happen for a verified order; never guess
            self._reset(s)
            return self._say(s, p(s.lang, "how_help"))
        return self._say(s, self._order_line(s, order) + p(s.lang, "order_problem_hint") + " " + p(s.lang, "anything_else"))

    def _order_line(self, s: CallSession, order: dict[str, Any]) -> str:
        o = public_order(order)
        status = o["status_label"] if s.lang == "en" else i18n.status_label(s.lang, o["status"], o["status_label"])
        msg = p(s.lang, "order_status", n=o["order_number"], status=status)
        if o["estimated_delivery"] and o["status"] in ("processing", "shipped", "out_for_delivery"):
            msg += p(s.lang, "order_eta", date=spoken_date(s.lang, o["estimated_delivery"]))
        if o["carrier"] and o["tracking_number"] and o["status"] in ("shipped", "out_for_delivery"):
            msg += p(s.lang, "order_carrier", carrier=o["carrier"], tracking=o["tracking_number"])
        return msg

    # ---- customer-care requests (complaint, return, simulated refund, request for the team) --------------------------------
    def _start_care(self, s: CallSession, kind: str, text: str, named: str | None) -> OutboundTurn:
        # Words of their own (a sentence, not just "I want a refund") become the description, read back before submitting.
        words = len(text.split())
        s.care = {"kind": kind, "category": infer_category(kind, text), "description": care._clean(text, 1000) if words >= 8 else None,
                  "item_id": None, "whole": False, "noted": False, "choices": [], "key": f"phone_{secrets.token_urlsafe(18)}",
                  "said": text}
        if kind == "escalation":
            lead = p(s.lang, "no_live_agent")
        else:
            lead = p(s.lang, "care_start", kind=KIND_NAMES[kind][s.lang])
        return self._need_order(s, "care", named, lead=lead)

    def _care_next(self, s: CallSession, lead: str = "") -> OutboundTurn:
        """Ask for the next missing piece of the request, or read it back for confirmation. Eligibility, items and open
        requests come from app/care_requests.py, for the verified order only."""
        c, L = s.care, s.lang
        kind = c["kind"]
        kind_name = KIND_NAMES[kind][L]
        lead = (lead + " ") if lead else ""
        try:
            opts = care.options(s.store, s.verified_customer_id, kind, s.verified_order)
        except CommerceError:
            self._reset(s)
            return self._say(s, lead + p(L, "not_submitted", reason="") + p(L, "how_help"))
        order = opts["order"]
        if not order["eligible"]:
            self._reset(s)
            if kind in ("return", "refund"):
                s.state = "care_offer"             # 1 = complaint, 2 = request for the team, anything else = main menu
                return self._say(s, lead + p(L, "not_eligible", kind=kind_name, n=s.verified_order, reason=_reason(L, order))
                                 + p(L, "offer_other"))
            return self._say(s, lead + p(L, "not_eligible", kind=kind_name, n=s.verified_order, reason=_reason(L, order)))
        if kind == "return" and not c["noted"] and order.get("until"):
            until = date.fromisoformat(order["until"])
            lead += p(L, "return_window", n=s.verified_order, date=spoken_date(L, until - timedelta(days=order["days"])),
                      days=order["days"], until=spoken_date(L, until)) + " "
            c["noted"] = True
        items = opts["items"]
        # Item: a return needs one; a complaint may be about one item or the whole order; refunds and team requests are per order.
        if c["item_id"] is None and not c["whole"] and kind in ("return", "complaint"):
            named = self._items_named(c.get("said") or "", items)
            if len(items) == 1:
                c["item_id"] = items[0]["id"]
            elif len(named) == 1:                  # "my headlamp is broken": that item, read back at the review
                c["item_id"] = named[0]
            elif items:
                shown = items[:9]
                c["choices"] = [i["id"] for i in shown]
                s.state = "care_item"
                text = p(L, "ask_item") + " " + " ".join(p(L, "option", name=i["name"], n=n + 1) for n, i in enumerate(shown))
                if kind == "complaint":
                    text += " " + p(L, "option_whole")
                return self._say(s, lead + text)
        # An open request of the same kind for this item (or order) already exists: say so instead of collecting more.
        existing = (next((i["open_request"] for i in items if i["id"] == c["item_id"]), None) if c["item_id"]
                    else opts.get("open_for_order"))
        if existing:
            self._reset(s)
            return self._say(s, lead + p(L, "duplicate", ref=existing, spelled=spelled(existing)) + " " + p(L, "anything_else"))
        if c["category"] is None:
            cats = list(care.CATEGORIES[kind])
            c["choices"] = cats
            s.state = "care_category"
            return self._say(s, lead + p(L, "ask_category") + " "
                             + " ".join(p(L, "option", name=CATEGORY_NAMES[cat][L], n=n + 1) for n, cat in enumerate(cats)))
        if not c["description"]:
            s.state = "care_description"
            return self._say(s, lead + p(L, "ask_description"))
        s.state = "care_confirm"
        item_name = next((i["name"] for i in items if i["id"] == c["item_id"]), None)
        text = p(L, "review", kind=kind_name[:1].upper() + kind_name[1:], order=p(L, "about_order", n=s.verified_order),
                 item=p(L, "about_item", name=item_name) if item_name else "", category=CATEGORY_NAMES[c["category"]][L],
                 desc=c["description"])
        if kind == "refund":
            text += p(L, "refund_note")
        return self._say(s, lead + text)

    def _on_offer(self, s: CallSession, text: str, digits: str) -> OutboundTurn:
        choice = self._choice(text, digits, 2)
        kind = {1: "complaint", 2: "escalation"}.get(choice or -1)
        if kind is None and text and (care_detect(text) or _PHONE_HUMAN.search(text) or _YES.search(text) is None):
            s.state = "main"
            return self._on_main(s, text, digits)
        if kind is None:                           # a bare "yes": ask which of the two
            return self._say(s, p(s.lang, "choice_not_caught") + p(s.lang, "offer_other"))
        s.state = "main"
        return self._start_care(s, kind, text if choice is None else "", s.verified_order)

    def _on_item(self, s: CallSession, text: str, digits: str) -> OutboundTurn:
        c = s.care
        choice = self._choice(text, digits, len(c["choices"]))
        if choice == 0 and c["kind"] == "complaint":
            c["whole"] = True
        elif choice:
            c["item_id"] = c["choices"][choice - 1]
        else:
            names = self._item_names(s)
            picked = next((i for i, n in names.items() if n.lower() in (text or "").lower()), None)
            if picked is None:
                return self._missed(s, p(s.lang, "choice_not_caught"))
            c["item_id"] = picked
        s.misses = 0
        return self._care_next(s)

    def _on_category(self, s: CallSession, text: str, digits: str) -> OutboundTurn:
        c = s.care
        choice = self._choice(text, digits, len(c["choices"]))
        picked = c["choices"][choice - 1] if choice else infer_category(c["kind"], text or "")
        if picked is None and text:
            said = text.strip().lower().rstrip(".।")
            picked = next((cat for cat in c["choices"] if any(n.lower() == said for n in CATEGORY_NAMES[cat].values())), None)
        if picked is None:
            return self._missed(s, p(s.lang, "choice_not_caught"))
        c["category"], s.misses = picked, 0
        return self._care_next(s)

    def _on_description(self, s: CallSession, text: str, digits: str) -> OutboundTurn:
        if not text:
            return self._missed(s, p(s.lang, "silence"))
        if sensitive_kind(text):
            # Never stored, never repeated back.
            return self._say(s, p(s.lang, "sensitive"))
        s.care["description"], s.misses = care._clean(text, 1000), 0
        return self._care_next(s)

    def _on_confirm(self, s: CallSession, text: str, digits: str) -> OutboundTurn:
        key = re.sub(r"\D", "", digits or "") or (code_digits(text) if text else "")
        if key == "1" or (text and _YES.search(text)):
            return self._submit(s)
        if key == "2" or (text and (_NO.search(text) or _CANCEL.search(text))):
            self._reset(s)
            return self._say(s, p(s.lang, "cancelled") + " " + p(s.lang, "anything_else"))
        return self._missed(s, p(s.lang, "review_again"), reprompt=False)

    def _submit(self, s: CallSession) -> OutboundTurn:
        """Only after an explicit yes. Success is reported ONLY with the reference the database returned."""
        c, L = s.care, s.lang
        kind = c["kind"]
        try:
            view, _created = care.create(s.store, s.verified_customer_id, kind=kind, category=c["category"],
                                         description=c["description"], order_number=s.verified_order, item_id=c["item_id"],
                                         idempotency_key=c["key"])
        except CommerceError as e:
            self._reset(s)
            if e.code == "duplicate_request":
                ref = (e.details or [{}])[0].get("issue", "")
                return self._say(s, p(L, "duplicate", ref=ref, spelled=spelled(ref)) + " " + p(L, "anything_else"))
            reason = e.message if L == "en" else (_reason(L, {"reason": (e.details or [{}])[0].get("issue")}) or "")
            return self._say(s, p(L, "not_submitted", reason=reason) + " " + p(L, "anything_else"))
        self._reset(s)
        ref = view["reference"]
        text = p(L, "submitted", kind=KIND_NAMES[kind][L], ref=ref, spelled=spelled(ref), status=_status_name(L, view["status"]))
        text += p(L, "submitted_follow")
        if kind == "escalation":
            text += p(L, "submitted_escalation")
        if kind == "refund":
            text += p(L, "refund_note")
        return self._say(s, text + " " + p(L, "anything_else"))

    def _care_status(self, s: CallSession) -> OutboundTurn:
        """Requests about the verified order only (a reference for another order gets the same answer as an unknown one)."""
        L, want = s.lang, (s.care or {})
        self._reset(s)
        rows = [r for r in care.list_for_customer(s.store, s.verified_customer_id, want.get("status_kind"))
                if r["order_number"] == s.verified_order]
        if want.get("reference"):
            rows = [r for r in rows if r["reference"] == want["reference"]]
        if not rows:
            return self._say(s, p(L, "status_none", n=s.verified_order) + " " + p(L, "anything_else"))
        lines = []
        for r in rows[:3]:
            full = care.get_for_customer(s.store, s.verified_customer_id, r["reference"])
            line = p(L, "status_line", ref=r["reference"], kind=KIND_NAMES[r["kind"]][L], status=_status_name(L, r["status"]))
            staff = [u for u in full["updates"] if u["by"] == "staff" and u["message"]]
            if staff:
                line += p(L, "status_reply", msg=staff[-1]["message"])
            lines.append(line)
        return self._say(s, " ".join(lines) + " " + p(L, "anything_else"))

    # ---- helpers -----------------------------------------------------------------------------------------------------
    def _new_request(self, s: CallSession, text: str) -> OutboundTurn | None:
        """While waiting for an order number or code, a caller who asks something else is not stuck: the question is
        handled from the main menu (any half-collected request is dropped, nothing was recorded)."""
        if not text or not re.search(r"[^\W\d_]", text) or code_digits(text):
            return None
        found = care_detect(text)
        wants_person = found is None and _PHONE_HUMAN.search(text)
        other = detect_intent(text).intents - {"order_status"}
        if not (found or wants_person or other):
            return None
        if found and found.get("kind") and s.care and found["kind"] == s.care.get("kind") and not found.get("status"):
            return None                            # repeating the same request ("it's a refund") is not a new one
        self._reset(s)
        return self._on_main(s, text, "")

    def _missed(self, s: CallSession, sorry: str, reprompt: bool = True) -> OutboundTurn:
        s.misses += 1
        if s.misses >= MAX_MISSES:
            self._reset(s)
            return self._say(s, p(s.lang, "back_to_menu") + " " + p(s.lang, "how_help"))
        return self._say(s, sorry + (" " + self._current_question(s) if reprompt else ""))

    def _current_question(self, s: CallSession) -> str:
        if s.state == "await_order_number":
            return p(s.lang, "ask_order", prefix=self._prefix(s))
        if s.state == "await_postal":
            return self._postal_prompt(s)
        if s.state in ("care_item", "care_category", "care_confirm") and s.care:
            if s.state == "care_item":
                s.care["item_id"] = None
            if s.state == "care_category":
                s.care["category"] = None
            return self._care_next(s).say
        if s.state == "care_description":
            return p(s.lang, "ask_description")
        return p(s.lang, "how_help")

    @staticmethod
    def _choice(text: str, digits: str, n: int) -> int | None:
        """1..n from a key press, a spoken digit or an ordinal ("the second one", "இரண்டாவது", "दूसरा"); 0 = whole order."""
        raw = re.sub(r"\D", "", digits or "") or (code_digits(text) if text else "")
        if raw and len(raw) == 1 and 0 <= int(raw) <= n:
            return int(raw)
        for i, rx in enumerate(_ORDINALS):
            if i < n and text and re.search(rx, text, re.I):
                return i + 1
        return None

    @staticmethod
    def _items_named(text: str, items: list[dict[str, Any]]) -> list[int]:
        """Items whose name shares a distinctive word (4+ letters, not a number) with what the caller said."""
        said = set(re.findall(r"[^\W\d_]{4,}", text.lower()))
        return [i["id"] for i in items if said & set(re.findall(r"[^\W\d_]{4,}", i["name"].lower()))]

    def _item_names(self, s: CallSession) -> dict[int, str]:
        try:
            opts = care.options(s.store, s.verified_customer_id, s.care["kind"], s.verified_order)
        except CommerceError:
            return {}
        return {i["id"]: i["name"] for i in opts["items"]}

    @staticmethod
    def _explicit_language(text: str) -> str | None:
        words = [w for w in re.split(r"[\s,.!?।]+", text.lower()) if w]
        if not words or len(words) > 4 or "nadu" in words:
            return None
        for lang, names in LANGUAGE_WORDS.items():
            if any(w in names for w in words):
                return lang
        return None

    def _contact_line(self, s: CallSession) -> str:
        prof = self._profile(s.store)
        return p(s.lang, "contact_only", store=self._store_name(s.store), email=prof.get("support_email", ""),
                 hours=prof.get("support_hours", ""))

    @staticmethod
    def _reset(s: CallSession) -> None:
        s.state, s.purpose, s.care, s.pending_order_number, s.misses = "main", None, None, None, 0

    @staticmethod
    def _profile(store: StoreId) -> dict[str, Any]:
        return repo.get_store_profile(store) or {}

    def _store_name(self, store: StoreId) -> str:
        # Without a trailing full stop: "Summit Trail Co." would otherwise be read as "Summit Trail Co.." in a sentence.
        return (self._profile(store).get("name") or STORE_BRANDING[store]["name"]).rstrip(".")

    @staticmethod
    def _say(s: CallSession, text: str) -> OutboundTurn:
        return OutboundTurn(s.call_id, re.sub(r"\s+", " ", text).strip(), language=s.lang)

    # The wording follows the store's market, never the order (looking the order up before verification would reveal
    # whether it exists). India stores ask for the six-digit PIN code; orders placed before the India launch were US
    # orders, so their ZIP code is still accepted and named. A US-market store keeps the original ZIP wording.
    def _india(self, store: StoreId) -> bool:
        view = getattr(self.assistant, "view", None)
        return bool(view is not None and view.market(store) == "IN")

    @staticmethod
    def _prefix(s: CallSession) -> str:
        return ORDER_PREFIX[s.store].rstrip("-")

    def _postal_prompt(self, s: CallSession) -> str:
        return p(s.lang, "ask_pin" if self._india(s.store) else "ask_zip")

    def _end(self, s: CallSession, say: str) -> OutboundTurn:
        s.state = "ended"
        return OutboundTurn(s.call_id, say, expect_input=False, hang_up=True, language=s.lang)

    @staticmethod
    def _number_from_digits(store: StoreId, digits: str) -> str | None:
        return f"{ORDER_PREFIX[store]}{digits}" if re.fullmatch(r"\d{5}", digits or "") else None

    def _evict(self) -> None:
        now = self.clock()
        for cid in [c for c, s in self._sessions.items() if now - s.last_seen > SESSION_TTL_SECONDS or s.state == "ended"]:
            del self._sessions[cid]
        while len(self._sessions) >= MAX_SESSIONS:
            self._sessions.pop(next(iter(self._sessions)))

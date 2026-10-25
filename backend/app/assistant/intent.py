"""Deterministic intent detection and search-term extraction.

The backend — not the language model — decides which data to fetch. These rules
pick the intents; the service then calls fixed repository functions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ORDER_NUMBER_RE = re.compile(r"\b([A-Za-z]{2})[-\s]?(\d{5})\b")

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "order_status": ("my order", "order status", "track", "tracking", "where is my", "where's my", "package", "parcel",
                     "has it shipped", "when will it arrive", "when will my", "my orders", "order number", "delivery status"),
    "shipping": ("shipping", "ship ", "ships", "delivery", "deliver", "postage", "how long does it take", "expedited"),
    "returns": ("return", "refund", "exchange", "send back", "money back"),
    "warranty": ("warranty", "defect", "broken", "guarantee"),
    "payment": ("payment", "pay with", "paypal", "apple pay", "credit card", "gift card"),
    "stock": ("in stock", "stock", "available", "availability", "sold out", "have any left", "inventory"),
    "price": ("price", "cost", "how much", "cheap", "expensive", "budget", "under $", "$"),
    "product": ("recommend", "looking for", "do you have", "do you sell", "need a", "need some", "suggest", "best", "show me", "tell me about"),
    "contact": ("human", "agent", "representative", "real person", "speak to someone", "talk to someone", "contact", "phone number", "email you", "hours"),
    "greeting": (" hello", " hi ", " hi,", " hi!", " hey", "good morning", "good evening"),
}

_STOPWORDS = set(
    """a an the and or but if of for to in on at by with from about as is are was were be been am do does did
    i me my mine you your we our us it its this that these those what which who whom how when where why can could
    would should will shall may might must have has had any some much many more most less very just also than too
    please thanks thank hello hi hey there here want wanted need looking look show tell know like get got buy
    sell price cost costs stock available availability recommend suggest something good best cheap expensive item
    items product products store shop order orders today now one ones help question""".split()
)


@dataclass
class Intent:
    intents: set[str] = field(default_factory=set)
    order_number: str | None = None
    search_terms: list[str] = field(default_factory=list)


def normalise_order_number(text: str) -> str | None:
    m = ORDER_NUMBER_RE.search(text)
    return f"{m.group(1).upper()}-{m.group(2)}" if m else None


def extract_search_terms(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
    terms: list[str] = []
    for w in words:
        if w in _STOPWORDS:
            continue
        stem = w[:-1] if w.endswith("s") and len(w) > 4 and not w.endswith("ss") else w
        if stem not in terms:
            terms.append(stem)
    return terms[:8]


def detect_intent(message: str) -> Intent:
    text = f" {message.lower().strip()} "
    found = {name for name, keys in _KEYWORDS.items() if any(k in text for k in keys)}
    order_number = normalise_order_number(message)
    if order_number:
        found.add("order_status")
    # "delivery" inside an order question is about that order, not the shipping policy.
    if "order_status" in found and not any(k in text for k in ("shipping cost", "shipping policy", "how much is shipping")):
        found.discard("shipping")
    if found & {"price", "stock"}:
        found.add("product")
    terms = [] if found <= {"order_status", "greeting", "contact"} and found else extract_search_terms(message)
    if not found and terms:
        found.add("product")
    return Intent(intents=found, order_number=order_number, search_terms=terms)

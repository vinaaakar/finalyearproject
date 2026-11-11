"""What the system can truthfully say.

Store policy text lives in the database and is written by people; it can describe services this
application does not provide (payment brands, prepaid return labels, store credit). The assistant must
never repeat such claims as fact, so every policy shown to the customer or to the language model goes
through `verified_policies`:

- PAYMENT answers come from the configured payment provider's real capabilities, never from the
  policy text (only a sandbox provider exists today, so no card brand, UPI, wallet or gift card is
  accepted).
- RETURNS / SHIPPING / WARRANTY text is kept, minus any sentence that promises a capability this system
  does not have (detected in English, Tamil and Hindi). Business rules (return windows, fees) stay.

The underlying database text is NOT changed here (that needs a reviewed data migration). Instead,
`policy_content_warnings` reports the unsupported claims so they can be corrected; it is logged at
start-up and exposed by /api/health.

Refunds: the schema has no refund records and no return/refund states beyond the order status
`returned`. So the assistant can never know that a refund was requested, approved, pending, completed
or failed, and must not imply any of them (see `REFUND_STATES`).
"""

from __future__ import annotations

import re
from typing import Any

# ---- refunds ---------------------------------------------------------------------------------------
# Distinctions the assistant would need to report a refund truthfully, and whether the backend can
# currently establish each one. None of them can: there is no refund table, no refund field on orders or
# payments, and the payments.status check constraint has no 'refunded' value.
REFUND_STATES: dict[str, bool] = {
    "return_requested": False,
    "return_approved": False,
    "item_returned": True,      # only as the order status `returned` (set by staff/seed data)
    "refund_pending": False,
    "refund_completed": False,
    "refund_failed": False,
}


def refund_evidence(order: dict[str, Any]) -> str:
    """'none' — there is never authoritative refund evidence in the current schema. Kept as a function so
    a future refunds model can return 'pending' / 'completed' / 'failed' from real records."""
    return "none"


# ---- unsupported claims in policy text -----------------------------------------------------------------
# Capability claims this application cannot honour. Each pattern matches one sentence's claim in any of the
# three languages. (Payment text is never used at all, so payment brands are listed only for the warnings.)
_CLAIMS: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "returns": [
        ("prepaid return label", re.compile(r"prepaid label|prepaid return label|முன்கட்டண லேபிள|प्रीपेड लेबल", re.I)),
        ("store credit", re.compile(r"store credit|ஸ்டோர் கிரெடிட்|स्टोर क्रेडिट", re.I)),
    ],
    "payment": [
        ("card / wallet / gift-card payments",
         re.compile(r"visa|mastercard|american express|amex|discover|paypal|apple pay|google pay|gift card|கிஃப்ட் கார்டு|गिफ़्ट कार्ड|"
                    r"major cards|முக்கிய கார்டுகள்|प्रमुख कार्ड", re.I)),
    ],
}
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?।])\s+")


def _unsupported(topic: str, sentence: str) -> list[str]:
    return [name for name, rx in _CLAIMS.get(topic, []) if rx.search(sentence)]


def strip_unsupported(topic: str, text: str) -> str:
    """Drop sentences that promise a capability this system lacks; keep everything else verbatim."""
    sentences = _SENTENCE_SPLIT.split(text.strip())
    kept = [s for s in sentences if not _unsupported(topic, s)]
    return " ".join(kept)


def policy_content_warnings(raw: dict[str, dict[str, str]]) -> list[str]:
    """Unsupported claims found in a store's stored policy text (English rows), e.g. ['payment: card / wallet …']."""
    found: list[str] = []
    for topic, p in raw.items():
        # The system's own capability statement (written by migration 0004) is truthful even though it names the
        # payment methods it does NOT accept.
        if topic == "payment" and {p.get("summary", ""), p.get("details", "")} <= _CAPABILITY_TEXTS:
            continue
        for name in sorted({n for part in (p.get("summary", ""), p.get("details", "")) for n in _unsupported(topic, part)}):
            found.append(f"{topic}: {name}")
    return found


PAYMENT_CAPABILITY = {
    "sandbox": {
        "ta": "இப்போது இந்த ஸ்டோரில் சோதனை (sandbox) பணம் செலுத்துதல் மட்டுமே உள்ளது: உண்மையான பணம் எதுவும் நகராது. கார்டுகள், UPI, "
              "வாலெட்டுகள், கிஃப்ட் கார்டுகள் அல்லது கேஷ் ஆன் டெலிவரி இன்னும் ஏற்றுக்கொள்ளப்படுவதில்லை.",
        "en": "Right now this store only takes test-mode (sandbox) payments: no real money moves. Cards, UPI, wallets, gift cards and "
              "cash on delivery are not accepted yet.",
        "hi": "अभी यह स्टोर सिर्फ़ टेस्ट-मोड (sandbox) भुगतान लेता है: कोई असली पैसा नहीं कटता। कार्ड, UPI, वॉलेट, गिफ़्ट कार्ड और "
              "कैश ऑन डिलीवरी अभी स्वीकार नहीं किए जाते।",
    },
    "unavailable": {
        "ta": "இப்போது இந்த ஸ்டோரில் ஆன்லைன் பணம் செலுத்தும் வசதி இல்லை.",
        "en": "Online payment isn't available in this store right now.",
        "hi": "अभी इस स्टोर में ऑनलाइन भुगतान उपलब्ध नहीं है।",
    },
}


_CAPABILITY_TEXTS = {text for texts in PAYMENT_CAPABILITY.values() for text in texts.values()}


def payment_capability_text(payments: Any, lang: str) -> str:
    key = "sandbox" if payments is not None and getattr(payments, "sandbox", False) else "unavailable"
    return PAYMENT_CAPABILITY[key].get(lang, PAYMENT_CAPABILITY[key]["en"])


def verified_policies(policies: dict[str, dict[str, str]], payments: Any, lang: str) -> dict[str, dict[str, str]]:
    """Policies safe to show or to give the language model (see module docstring)."""
    out: dict[str, dict[str, str]] = {}
    for topic, p in policies.items():
        if topic == "payment":
            text = payment_capability_text(payments, lang)
            out[topic] = {"summary": text, "details": text}
        else:
            summary = strip_unsupported(topic, p["summary"])
            details = strip_unsupported(topic, p["details"])
            dropped = [s for s in _SENTENCE_SPLIT.split(p["details"].strip()) if _unsupported(topic, s)]
            # A dropped sentence may also have carried a real business rule (e.g. "within 30 days … or store credit"):
            # keep the summary, which states that rule without the unsupported claim.
            if summary and any(re.search(r"\d", s) for s in dropped) and summary not in details:
                details = f"{summary} {details}".strip()
            out[topic] = {"summary": summary or details, "details": details or summary}
    return out


# ---- reply hygiene -------------------------------------------------------------------------------------
# Unresolved template variables, bracketed placeholders, links and markdown must never reach a customer.
_PLACEHOLDER_RE = re.compile(
    r"\[[^\]\n]{0,60}\]|\{[A-Za-z_][\w.]*\}|<[A-Za-z/][^>\n]{0,60}>|\binsert (a |the )?(link|url|name|here)\b|\bplaceholder\b|"
    r"\bTODO\b|\bTBD\b|lorem ipsum|\bXXX+\b",
    re.I,
)
_LINK_RE = re.compile(r"https?://|www\.|\]\(|\*\*|__|^#{1,6}\s", re.I | re.M)


def has_placeholder(text: str) -> bool:
    return bool(_PLACEHOLDER_RE.search(text or ""))


def has_link_or_markup(text: str) -> bool:
    return bool(_LINK_RE.search(text or ""))


# ---- vocabulary grounding for model replies ------------------------------------------------------------
# A model reply that rephrases verified facts reuses their words. Content words that appear nowhere in the
# facts, the draft or the customer's message ("parka", "insulated", "four-season") are how invented products
# and advice show up. Common conversational words are allowed; more than MAX_NOVEL_WORDS others → rejected.
MAX_NOVEL_WORDS = 3
_CONVERSATIONAL = set("""
about above absolutely actually additional after again ahead allow almost already also although always another
answer anything appreciate around assist assistance available away based because before being below best better
between bring business call can't cannot certainly change charge charges check choose choosing clear come comes
complete contact correct could customer customers days definitely delighted detail details different directly does
doesn't don't during each either email enjoy enough ensure every everything example exactly feel find fine first
following free friendly further give glad good great guide happy have having hello help helpful here hope however
idea important include included including information instead interested items just keep kind know learn least
less let's like likely little look looking made make makes many may maybe mean means more most much need needs
never next nice note offer offers only order orders other otherwise our ours over particular perfect place please
pleased plus possible prefer price prices probably provide question questions quick quickly rather really reach
ready reason recommend regarding related remember reply request right same see send share shop should simply since
something soon sorry specific start store sure take takes team than thank thanks that's their them then there
therefore these they thing things think this those through time today together trouble typically unfortunately
until usually various very want wants welcome well what what's whatever when where whether which while within
without wonderful would you'd you'll you're your yours yourself
""".split())
_WORD_RE = re.compile(r"[a-z][a-z'\-]{4,}")


def novel_words(reply: str, allowed_text: str) -> list[str]:
    allowed = set(_WORD_RE.findall(allowed_text.lower())) | _CONVERSATIONAL

    def known(w: str) -> bool:
        stems = {w, w.rstrip("s"), w[:-2] if w.endswith("es") else w, w[:-3] if w.endswith("ing") else w,
                 w[:-2] if w.endswith("ed") else w, w[:-2] if w.endswith("ly") else w}
        return any(s in allowed or s + "s" in allowed or s + "e" in allowed for s in stems)

    return sorted({w for w in _WORD_RE.findall(reply.lower()) if not known(w.strip("'-"))})

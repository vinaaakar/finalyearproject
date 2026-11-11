"""Store policies for the store's market.

The policy rows in each store database were written for the original US demo ("free over $75", "contiguous US only").
For an India store those claims are wrong, so — without editing the stored rows — this module serves:
  * shipping: generated from the India shipping configuration (config/shipping/<store>.json), so the policy text, the
    checkout and the assistant always state the same fee; clearly labelled as an academic demonstration rate, with no
    delivery time promised (none is configured);
  * returns: the store's own rule, labelled as a demonstration policy.
A US-market store gets its stored policies unchanged. Tamil and Hindi texts need native-speaker review.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .markets import format_money
from .shipping_zones import load_zones
from .stores import StoreId

_SHIP = {
    "en": ("Demonstration rate: {fee} standard delivery anywhere in India{free_s}.",
           "Demonstration shipping for this academic project (not a real delivery service): standard delivery anywhere in "
           "India costs {fee}{free_d}. No delivery time is promised, and there is no expedited option.",
           ", free from {free}", ", free on orders of {free} or more"),
    "ta": ("மாதிரி கட்டணம்: இந்தியாவில் எங்கும் ஸ்டாண்டர்ட் டெலிவரி {fee}{free_s}.",
           "இது கல்வித் திட்டத்திற்கான மாதிரி (டெமோ) ஷிப்பிங் கட்டணம் — உண்மையான டெலிவரி சேவை அல்ல: இந்தியாவில் எங்கும் "
           "ஸ்டாண்டர்ட் டெலிவரிக்கு {fee}{free_d}. டெலிவரி நேரம் எதுவும் உறுதியளிக்கப்படவில்லை; விரைவு டெலிவரி வசதி இல்லை.",
           "; {free} முதல் இலவசம்", "; {free} அல்லது அதற்கு மேல் உள்ள ஆர்டர்களுக்கு இலவசம்"),
    "hi": ("डेमो दर: भारत में कहीं भी स्टैंडर्ड डिलीवरी {fee}{free_s}।",
           "यह शैक्षणिक प्रोजेक्ट के लिए डेमो शिपिंग दर है — कोई असली डिलीवरी सेवा नहीं: भारत में कहीं भी स्टैंडर्ड डिलीवरी "
           "{fee}{free_d}। डिलीवरी का कोई समय तय नहीं है, और एक्सप्रेस डिलीवरी उपलब्ध नहीं है।",
           ", {free} से मुफ़्त", ", {free} या उससे अधिक के ऑर्डर पर मुफ़्त"),
}
_SHIP_NONE = {
    "en": "Shipping rates for India haven't been configured yet, so orders can't be placed.",
    "ta": "இந்தியாவுக்கான ஷிப்பிங் கட்டணங்கள் இன்னும் அமைக்கப்படவில்லை, எனவே ஆர்டர் செய்ய இயலாது.",
    "hi": "भारत के लिए शिपिंग दरें अभी तय नहीं की गई हैं, इसलिए ऑर्डर नहीं किया जा सकता।",
}
DEMO_LABEL = {
    "en": "Demonstration policy (academic project): ",
    "ta": "மாதிரி கொள்கை (கல்வித் திட்டம்): ",
    "hi": "डेमो नीति (शैक्षणिक प्रोजेक्ट): ",
}


def shipping_text(store: StoreId, config_dir: Path, lang: str) -> dict[str, str]:
    lang = lang if lang in _SHIP else "en"
    zones = load_zones(config_dir, store, "IN")
    if not zones:
        return {"summary": _SHIP_NONE[lang], "details": _SHIP_NONE[lang]}
    summaries, details = [], []
    s_tpl, d_tpl, free_s, free_d = _SHIP[lang]
    for z in zones:
        fee = format_money(z["standard_cents"], z["currency"])
        free = format_money(z["free_over_cents"], z["currency"]) if z.get("free_over_cents") is not None else None
        summaries.append(s_tpl.format(fee=fee, free_s=free_s.format(free=free) if free else ""))
        details.append(d_tpl.format(fee=fee, free_d=free_d.format(free=free) if free else ""))
    return {"summary": " ".join(summaries), "details": " ".join(details)}


def for_market(store: StoreId, policies: dict[str, dict[str, str]], lang: str, market: str,
               config_dir: Path) -> dict[str, dict[str, str]]:
    if market != "IN":
        return policies
    out = dict(policies)
    out["shipping"] = shipping_text(store, config_dir, lang)
    label = DEMO_LABEL.get(lang, DEMO_LABEL["en"])
    if "returns" in out:
        out["returns"] = {k: label + v for k, v in out["returns"].items()}
    return out


def policies_for(store: StoreId, settings: Any, lang: str, raw: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    return for_market(store, raw, lang, settings.store_markets.get(store.value, "US"), settings.shipping_config_dir)

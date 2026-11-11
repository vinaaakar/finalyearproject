"""Per-utterance language identification for Tamil, English and Hindi.

The language is inferred from WHAT THE CUSTOMER SAID, every message, independently:

1. Text evidence (always): the script of each word (Tamil script, Devanagari, Latin), plus a
   small vocabulary of romanized Tamil / Hindi function words ("enga", "irukka", "kya", "hai").
   Identifiers such as order numbers, prices and product names do not count as language evidence.
2. Acoustic evidence (voice only): whisper.cpp's language detection on the audio. It is used only
   when it arrives in a speech receipt signed by this server (see `speech_receipt`), so a client
   cannot inject a language claim.

Decision policy:
- Native script dominates: if ≥ 30 % of the words are Tamil (or Devanagari) script, the utterance
  is Tamil (or Hindi). People speaking English do not produce Tamil-script words; a Tamil sentence
  with an English product name is still Tamil (code-switching is preserved, not "corrected").
- Latin text is English unless romanized Tamil/Hindi function words dominate.
- Acoustic + text agree → confident. They disagree → the stronger evidence wins only if it is
  clearly stronger; otherwise the result is UNCERTAIN and the assistant asks which language.
- No language evidence at all (e.g. just "SA-10001" or "ok") → `neutral`: the reply uses the
  current conversation language, and the response says the language was not detected.

The conversation language, UI selector and browser locale are never used as detection evidence.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass

SUPPORTED = ("ta", "en", "hi")
BCP47 = {"ta": "ta-IN", "en": "en-IN", "hi": "hi-IN"}

_TAMIL = re.compile(r"[஀-௿]")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_ARABIC = re.compile(r"[؀-ۿ]")  # whisper sometimes writes spoken Hindi in Urdu script
_LATIN = re.compile(r"[A-Za-z]")
# Other Indian scripts (Bengali, Gurmukhi, Gujarati, Odia, Telugu, Kannada, Malayalam, Sinhala): a language the store
# does not support. Answering such text in the conversation language could be unreadable to the customer → clarify.
_OTHER_INDIC = re.compile(r"[\u0980-\u0B7F\u0C00-\u0DFF]")
# Identifiers are not language evidence.
_IDENTIFIER = re.compile(r"\b[A-Za-z]{2}-?\d{3,}\b|\$\s?\d[\d,.]*|\b\d[\d,.:/-]*\b|\b[0-9A-Z]{8,}\b")

ROMANIZED = {
    # Tanglish: Tamil written in Latin letters, usually mixed with English nouns ("Ennoda order enga irukku?",
    # "Cart la irukkura products sollunga"). Function words, pronouns, case endings and verb forms only — never
    # product or shopping nouns, which are shared with English.
    "ta": set("""enga enge engey enna ennoda en naan nan neenga unga ungal ungalidam irukku irukka irukkaa irukkiratha
        irukkudha iruka venum vendum venam evvalavu evlo eppo eppadi epdi sollunga sollu illa illai irukum
        kidaikkuma kidaikum anuppunga vanakkam nandri romba konjam paarunga theriyuma theriyum aachu ennachu
        enakku enaku ennudaya ennudaiya ungaloda indha intha andha antha idha itha adha atha idhu ithu adhu athu
        oda la kulla ulla kitta kitte thaan dhaan irukkura irukura iruku irukkuma varum varuma varala vandhuchu
        vanthuchu vandhucha vanthucha aagum aguma aacha aachaa achu pannunga pannu panni pannanum pannalama
        pannalaam pannidunga solla theriyanum therinjukanum seiyanum seyyanum seiyalama seiyanumnu epo yen yaar
        roobai roobaikku rubai rubaikku rupai kudunga kodunga podunga podu sethu serthu serunga paakanum paarkanum
        paathu mudiyuma mudiyum vaanganum vanganum vaangalam nalla eduthudunga edunga""".split()),
    "hi": set("""kya kyaa hai hain mera meri mere mujhe aap aapke aapka kahan kahaan kab kitna kitne kitni chahiye
        nahi nahin karna kaise kaisa batao bataiye hoga milega bhej bhejo namaste dhanyavad shukriya tak abhi
        wala wali kripya mein aur ke ki ka ko se aayega aaega hua huaa wapas vapas karo kariye dikhao dikhaiye
        chahie kaun kaunsa sabse sasta mujhko kidhar""".split()),
}
# Common English function words: evidence that Latin text is English rather than romanized Tamil/Hindi.
# Shopping nouns that Tanglish and Hinglish borrow from English ("order", "status", "price", "return", "delivery") are
# deliberately NOT here: "Enakku order status theriyanum" is Tamil with English nouns, not English.
_ENGLISH = set("""the a an is are was do does did you your my me i we can could would will what where when how which
    have has any some please much in on for to of and or with this that it there here want need looking get
    tell show""".split())


@dataclass(frozen=True)
class LanguageResult:
    language: str | None      # "ta" | "en" | "hi", or None when uncertain/neutral
    status: str               # "detected" | "uncertain" | "neutral"
    source: str               # "text" | "speech+text" | "speech" | "none"
    confidence: float         # 0..1, rough
    detail: str = ""          # short reason (for tests/logs; never contains user text)


def text_evidence(text: str) -> tuple[dict[str, float], int]:
    """Returns (score per language in 0..1, number of language-bearing words)."""
    cleaned = _IDENTIFIER.sub(" ", text)
    words = [w for w in re.split(r"[\s,.!?;:()\"'।]+", cleaned) if w]
    counts = {"ta": 0, "hi": 0, "en": 0}
    arabic = 0
    latin_words: list[str] = []
    for w in words:
        if _TAMIL.search(w):
            counts["ta"] += 1
        elif _DEVANAGARI.search(w):
            counts["hi"] += 1
        elif _ARABIC.search(w):
            arabic += 1
        elif _LATIN.search(w):
            latin_words.append(w.lower())
    roman = {k: sum(w in v for w in latin_words) for k, v in ROMANIZED.items()}
    english = sum(w in _ENGLISH for w in latin_words)
    best_roman = max(roman, key=roman.get)
    # A Latin word counts toward a romanized language only if that language's function words outnumber English ones.
    if roman[best_roman] > english and roman[best_roman] >= 1:
        counts[best_roman] += len(latin_words)
    elif english >= 1:
        counts["en"] += len(latin_words)
    # else: Latin words with no function words at all (product names, "ok", other languages) are not evidence.
    total = sum(counts.values())
    if arabic and arabic >= total:
        # Urdu-script transcript: whisper writes spoken Hindi this way, but also some misheard clips.
        # Weak Hindi evidence only (0.6): decisive only together with confident acoustic Hindi.
        return {"hi": 0.6, "ta": 0.0, "en": 0.0}, total + arabic
    total += arabic
    if total == 0:
        return {k: 0.0 for k in counts}, 0
    scores = {k: v / total for k, v in counts.items()}
    # Native script dominates mixed utterances (code-switching with English nouns is normal).
    for native, other in (("ta", "hi"), ("hi", "ta")):
        if scores[native] >= 0.3 and counts[native] >= counts[other]:
            conf = max(0.75, scores[native])
            return {native: conf, other: 0.0, "en": 1 - conf}, total
    return scores, total


def identify(text: str, acoustic: tuple[str, float] | None = None) -> LanguageResult:
    """Identify the language of one utterance. `acoustic` = (language, probability) from a VERIFIED speech receipt."""
    scores, n_words = text_evidence(text)
    text_lang = max(scores, key=scores.get) if n_words else None
    text_conf = scores[text_lang] if text_lang else 0.0
    # Very short Latin text ("ok", "yes", "tent") is weak evidence of English.
    if text_lang == "en" and n_words <= 1:
        text_conf = min(text_conf, 0.5)

    # Text evidence strong enough to stand on its own: native Tamil/Devanagari script, or a fluent English sentence.
    strong_text = (text_lang in ("ta", "hi") and text_conf >= 0.75) or (text_lang == "en" and text_conf >= 0.9 and n_words >= 3)
    if acoustic and acoustic[0] not in SUPPORTED:
        # The speech engine heard a language we don't support (e.g. Telugu, French), however weakly.
        # Never let weak text (Urdu script, product names) turn that into a confident supported language.
        if strong_text:
            return LanguageResult(text_lang, "detected", "speech+text", text_conf, "strong transcript, unsupported speech")
        return LanguageResult(None, "uncertain", "speech", acoustic[1], "unsupported spoken language")
    if acoustic:
        a_lang, a_p = acoustic
        if text_lang is None:
            return (LanguageResult(a_lang, "detected", "speech", a_p, "speech only")
                    if a_p >= 0.6 else LanguageResult(None, "uncertain", "speech", a_p, "weak speech, no text evidence"))
        if a_lang == text_lang:
            # Weak text evidence (e.g. an Urdu-script or one-word transcript) needs strong speech evidence.
            if text_conf < 0.75 and a_p < 0.75:
                return LanguageResult(None, "uncertain", "speech+text", max(a_p, text_conf), "weak agreement")
            return LanguageResult(a_lang, "detected", "speech+text", max(a_p, text_conf), "speech and text agree")
        # Disagreement: native script in the transcript is decisive (the engine wrote that script).
        if text_lang in ("ta", "hi") and text_conf >= 0.75:
            return LanguageResult(text_lang, "detected", "speech+text", text_conf, "transcript script outweighs speech")
        if a_p >= 0.8 and text_conf <= 0.5:
            return LanguageResult(a_lang, "detected", "speech+text", a_p, "strong speech, weak text")
        if text_conf >= 0.9 and n_words >= 3 and a_p < 0.7:
            return LanguageResult(text_lang, "detected", "speech+text", text_conf, "fluent text, weak speech")
        return LanguageResult(None, "uncertain", "speech+text", min(a_p, text_conf), "speech and text disagree")

    if text_lang is None:
        if len(_OTHER_INDIC.findall(text)) >= 2:
            return LanguageResult(None, "uncertain", "text", 0.0, "unsupported script")
        return LanguageResult(None, "neutral", "none", 0.0, "no language-bearing words")
    if text_conf <= 0.5:
        # e.g. a single English word like "price": could be part of any of the three languages.
        return LanguageResult(None, "neutral", "text", text_conf, "too little text")
    return LanguageResult(text_lang, "detected", "text", text_conf, "text")


# ---- speech receipts ------------------------------------------------------------------------------
# The transcribe endpoint signs (store, transcript hash, detected language, probability, expiry). The chat
# endpoint accepts the acoustic language only if the receipt verifies AND matches the message text exactly.

RECEIPT_TTL_SECONDS = 300


def _sign(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), b"speech-receipt:" + body.encode(), hashlib.sha256).hexdigest()


def speech_receipt(secret: str, store: str, text: str, language: str | None, probability: float | None) -> str:
    body = json.dumps({"s": store, "h": hashlib.sha256(text.strip().encode()).hexdigest(), "l": language,
                       "p": round(probability or 0.0, 3), "e": int(time.time()) + RECEIPT_TTL_SECONDS}, separators=(",", ":"))
    return body.encode().hex() + "." + _sign(secret, body)


def verify_receipt(secret: str, receipt: str | None, store: str, text: str) -> tuple[str, float] | None:
    if not receipt or "." not in receipt:
        return None
    body_hex, sig = receipt.rsplit(".", 1)
    try:
        body = bytes.fromhex(body_hex).decode()
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    if not hmac.compare_digest(sig, _sign(secret, body)):
        return None
    if data.get("s") != store or data.get("e", 0) < time.time():
        return None
    if data.get("h") != hashlib.sha256(text.strip().encode()).hexdigest():
        return None  # the receipt is for a different (e.g. edited) message
    lang = data.get("l")
    if not isinstance(lang, str) or not re.fullmatch(r"[a-z]{2,3}", lang):
        return None
    return lang, float(data.get("p", 0.0))

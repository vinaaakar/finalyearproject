"""Multilingual conversational-shopping acceptance tests for Scout (Store A) and Maple (Store B).

Text level (always run): Tamil default, automatic switching Tamil → English → Tamil → Hindi with the products under
discussion kept across every switch, no language drift over a long conversation, store-specific search, conversational
cart add/remove, clarification for unsupported scripts.

Voice level (run when AVC_TEST_WHISPER_MULTI_MODEL points at a multilingual whisper.cpp model): the same conversation
spoken by the macOS voices Vani (ta), Rishi (en) and Lekha (hi), clean and with added noise, transcribed by the local
whisper.cpp engine through /speech/transcribe and answered with the server's speech receipt. This is synthetic speech,
NOT a physical-microphone or native-speaker test (docs/voice-testing.md).
"""

from __future__ import annotations

import random
import re
import struct
import time
import uuid
import wave

import pytest

from .test_multilingual import HAS_ENGINE, _engine_client, _say_wav, script_of

# store → (four turns ta/en/ta/hi, products that the conversation is about, a product of the OTHER store)
SCENARIOS = {
    "store-a": (["வணக்கம், எனக்கு ஒரு நல்ல hiking bag வேண்டும்.", "Show me the best one under 5000 rupees.",
                 "இதில் எந்த நிறங்கள் கிடைக்கும்?", "मुझे इसकी कीमत बताइए।"],
                {"daytrip-22l-daypack", "trailhead-55l-backpack"}, "gooseneck-kettle"),
    "store-b": (["வணக்கம், எனக்கு நல்ல coffee beans வேண்டும்.", "Show me the best one under 20 dollars.",
                 "இதில் எந்த சுவைகள் உள்ளன?", "मुझे इसकी कीमत बताइए।"],
                {"ethiopia-yirgacheffe-beans", "house-blend-beans"}, "daytrip-22l-daypack"),
}
EXPECTED_LANGS = ["ta", "en", "ta", "hi"]
QUOTED = re.compile(r"“[^”]*”")


def reply_script(reply: str) -> str:
    """Script of the assistant's own words (quoted English catalogue descriptions removed)."""
    return script_of(QUOTED.sub(" ", reply))


def chat(c, store, message, history, conv, headers=None, receipt=None):
    body = {"message": message, "history": history[-8:], "channel": "web_voice" if receipt else "web_chat", "conversation_language": conv}
    if receipt:
        body["speech_receipt"] = receipt
    t0 = time.perf_counter()
    r = c.post(f"/api/stores/{store}/chat", json=body, headers=headers or {})
    assert r.status_code == 200, r.text
    j = r.json()
    j["_latency"] = time.perf_counter() - t0
    history.extend([{"role": "user", "content": message}, {"role": "assistant", "content": j["reply"]}])
    return j


# ---- text level ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_new_conversation_starts_in_tamil(client, store):
    """A first message with no language of its own (an emoji) is answered in Tamil — the default — without any selection."""
    r = client.post(f"/api/stores/{store}/chat", json={"message": "👍"}).json()
    assert r["language"] == "ta" and reply_script(r["reply"]) == "ta"


@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_switching_languages_keeps_the_products_under_discussion(client, store):
    turns, discussed, _ = SCENARIOS[store]
    history, conv = [], "ta"
    for message, lang in zip(turns, EXPECTED_LANGS):
        r = chat(client, store, message, history, conv)
        assert r["language"] == lang and r["language_status"] == "detected", (message, r["language"])
        assert reply_script(r["reply"]) == lang, r["reply"]
        slugs = {p["slug"] for p in r["products"]}
        assert slugs and slugs <= discussed, (message, slugs)          # the same products, in every language
        conv = r["language"]
    assert "can't apply" in history[3]["content"] or store == "store-b"   # Store A: a rupee budget is not converted to USD


@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_long_conversation_has_no_language_drift(client, store):
    asks = {"ta": ["திருப்பி அனுப்பும் கொள்கை என்ன?", "ஷிப்பிங் கட்டணம் எவ்வளவு?"],
            "en": ["What is your return policy?", "How much is shipping?"],
            "hi": ["आपकी वापसी नीति क्या है?", "शिपिंग कितनी है?"]}
    history, conv, seen = [], "ta", []
    for i in range(12):
        lang = ["ta", "en", "hi", "ta", "ta", "hi", "en", "en", "ta", "hi", "hi", "ta"][i]
        r = chat(client, store, asks[lang][i % 2], history, conv)
        seen.append((lang, r["language"], reply_script(r["reply"])))
        conv = r["language"]
    assert all(want == got == script for want, got, script in seen), seen


@pytest.mark.parametrize("store, other_words", [("store-a", "coffee beans and a kettle"), ("store-b", "a tent and hiking boots")])
def test_search_returns_only_this_stores_products(client, store, other_words):
    r = chat(client, store, f"Do you sell {other_words}?", [], "en")
    other = SCENARIOS["store-b" if store == "store-a" else "store-a"][1]
    assert not ({p["slug"] for p in r["products"]} & other)


@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_conversational_cart_add_and_remove_in_three_languages(client, store):
    turns, discussed, _ = SCENARIOS[store]
    reg = client.post(f"/api/stores/{store}/auth/register", json={"email": f"accept-{uuid.uuid4().hex[:8]}@example.com",
                                                                  "full_name": "Acceptance Shopper", "password": "Accept-Strong-Pass-42"})
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    history = []
    chat(client, store, turns[0], history, "ta", h)
    add = chat(client, store, "இதை கார்ட்டில் சேர்க்கவும்", history, "ta", h)                     # Tamil: add this
    act = next(a for a in add["actions"] if a["type"] == "add_to_cart")
    assert add["language"] == "ta" and act["slug"] in discussed
    assert client.get(f"/api/stores/{store}/cart", headers=h).json()["cart"]["item_count"] == 0   # nothing until the button
    client.post(f"/api/stores/{store}/cart/items", headers=h, json={"slug": act["slug"], "quantity": act["quantity"]})
    rem = chat(client, store, "इसे कार्ट से हटा दो", history, "ta", h)                              # Hindi: remove it
    ract = next(a for a in rem["actions"] if a["type"] == "remove_from_cart")
    assert rem["language"] == "hi" and ract["slug"] == act["slug"]
    assert client.get(f"/api/stores/{store}/cart", headers=h).json()["cart"]["item_count"] == 1   # still there until tapped
    client.delete(f"/api/stores/{store}/cart/items/{ract['slug']}", headers=h)
    empty = chat(client, store, "please remove it from my cart", history, "hi", h)                 # English, nothing left
    assert empty["language"] == "en" and empty["actions"] == [] and "nothing to remove" in empty["reply"]


@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_unsupported_language_asks_instead_of_guessing(client, store):
    r = client.post(f"/api/stores/{store}/chat", json={"message": "నాకు ఒక టెంట్ కావాలి", "conversation_language": "ta"}).json()
    assert r["clarification"] is True and r["language"] == "ta"


# ---- voice level (real local whisper.cpp; synthetic voices) -----------------------------------------------------------
VOICES = {"ta": "Vani", "en": "Rishi", "hi": "Lekha"}


def _noisy(wav_bytes: bytes, snr_db: float, seed: int = 7) -> bytes:
    import io
    with wave.open(io.BytesIO(wav_bytes)) as w:
        params, frames = w.getparams(), w.readframes(w.getnframes())
    s = struct.unpack(f"<{len(frames) // 2}h", frames)
    rms = (sum(x * x for x in s) / max(1, len(s)) / (10 ** (snr_db / 10))) ** 0.5
    rnd = random.Random(seed)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setparams(params)
        w.writeframes(struct.pack(f"<{len(s)}h", *(max(-32768, min(32767, int(x + rnd.gauss(0, rms)))) for x in s)))
    return out.getvalue()


@pytest.mark.skipif(not HAS_ENGINE, reason="set AVC_TEST_WHISPER_MULTI_MODEL to a multilingual ggml model")
@pytest.mark.parametrize("store", ["store-a", "store-b"])
@pytest.mark.parametrize("noise", [None, 15])
def test_spoken_conversation_switches_languages_and_keeps_context(settings, tmp_path, capsys, store, noise):
    turns, discussed, _ = SCENARIOS[store]
    rows, history, conv = [], [], "ta"
    with _engine_client(settings) as c:
        for i, (text, lang) in enumerate(zip(turns, EXPECTED_LANGS)):
            audio = _say_wav(tmp_path, f"{store}{i}", VOICES[lang], text)
            if noise:
                audio = _noisy(audio, noise)
            t0 = time.perf_counter()
            t = c.post(f"/api/stores/{store}/speech/transcribe", content=audio, headers={"Content-Type": "audio/wav"}).json()
            stt = time.perf_counter() - t0
            r = chat(c, store, t["text"], history, conv, receipt=t["speech_receipt"])
            outcome = "clarified" if r["clarification"] else r["language"]
            # Safety property: never a confidently WRONG language — right one, or a clarification.
            assert outcome in (lang, "clarified"), (t, r["reply"])
            heard, recovered = t["text"], False
            if r["clarification"]:
                # What the customer does in the chat: tap their language; the SAME audio is transcribed again in it
                # and sent as an explicit choice (ChatWidget.chooseLanguage).
                t2 = c.post(f"/api/stores/{store}/speech/transcribe?language={lang}", content=audio, headers={"Content-Type": "audio/wav"}).json()
                body = {"message": t2["text"], "history": history[-8:], "channel": "web_voice", "conversation_language": conv, "language_override": lang}
                r = c.post(f"/api/stores/{store}/chat", json=body).json()
                history.extend([{"role": "user", "content": t2["text"]}, {"role": "assistant", "content": r["reply"]}])
                heard, recovered = t2["text"], True
                assert r["language"] == lang and not r["clarification"]
            slugs = {p["slug"] for p in r["products"]}
            rows.append({"expected": lang, "heard": heard[:60], "whisper": t["detected_language"], "p": round(t["language_probability"] or 0, 2),
                         "outcome": outcome, "recovered_by_choice": recovered, "context_ok": bool(slugs) and slugs <= discussed,
                         "stt_s": round(stt, 2), "reply_s": round(r.get("_latency", 0), 2)})
            assert reply_script(r["reply"]) == lang, r["reply"]
            conv = r["language"]
    with capsys.disabled():
        print(f"\n  [{store} {'clean' if noise is None else f'{noise} dB SNR'}]")
        for row in rows:
            print(f"    {row}")
    if noise is None:
        # Measured with ggml-base on this Mac: at least 3 of 4 clean turns identified without help (the rest recovered
        # by the customer's one tap), and the conversation's products kept in at least 3 of 4 turns.
        assert sum(r["outcome"] == r["expected"] for r in rows) >= 3, rows
        assert sum(r["context_ok"] for r in rows) >= 3, rows


@pytest.mark.skipif(not HAS_ENGINE, reason="set AVC_TEST_WHISPER_MULTI_MODEL to a multilingual ggml model")
@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_unclear_audio_is_handled_gracefully(settings, store):
    """Noise only (no speech) never produces a wrong-language answer or an error page: empty text or a clarification."""
    import io
    rnd = random.Random(3)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(struct.pack("<32000h", *(int(rnd.gauss(0, 900)) for _ in range(32000))))
    with _engine_client(settings) as c:
        r = c.post(f"/api/stores/{store}/speech/transcribe", content=buf.getvalue(), headers={"Content-Type": "audio/wav"})
        assert r.status_code in (200, 422), r.text
        if r.status_code == 200 and r.json()["text"].strip():
            j = c.post(f"/api/stores/{store}/chat", json={"message": r.json()["text"], "speech_receipt": r.json()["speech_receipt"],
                                                          "conversation_language": "ta"}).json()
            assert j["clarification"] or j["language"] in ("ta", "en", "hi")

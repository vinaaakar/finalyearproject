"""Speech engine layer: whisper.cpp language identification restricted to Tamil/English/Hindi,
uncertainty flagging, English-model routing, per-language prompts and signed speech receipts.

The deterministic tests use a fake `whisper-cli` script. The real-engine tests synthesise speech
with macOS voices (Vani = Tamil, Lekha = Hindi, Samantha = English) and run whisper.cpp; they need
AVC_TEST_WHISPER_MULTI_MODEL (a multilingual ggml model) and are skipped otherwise.
No test here uses a physical microphone."""

import os
import shutil
import subprocess

import pytest

from app.speech.adapters import LANGUAGE_PROMPTS, WhisperCppSTT
from tests.conftest import make_client
from tests.test_assistant import FakeLLM, chat
from tests.test_speech import make_wav

FAKE_WHISPER = """#!/bin/sh
# Fake whisper-cli: reports $FAKE_LANG/$FAKE_P on detection, echoes its arguments on transcription.
model=""; lang=""; prompt="no"; detect="no"
while [ $# -gt 0 ]; do
  case "$1" in
    -m) model="$2"; shift ;;
    -l) lang="$2"; shift ;;
    --prompt) prompt="$2"; shift ;;
    -dl) detect="yes" ;;
  esac
  shift
done
if [ "$detect" = "yes" ]; then
  [ "$FAKE_LANG" = "none" ] || echo "whisper_full_with_state: auto-detected language: ${FAKE_LANG:-ta} (p = ${FAKE_P:-0.9})" >&2
  exit 0
fi
echo "model=$(basename "$model") lang=$lang prompt=$prompt"
"""


@pytest.fixture
def fake_engine(tmp_path):
    binary = tmp_path / "whisper-cli"
    binary.write_text(FAKE_WHISPER)
    binary.chmod(0o755)
    multi, en = tmp_path / "ggml-base.bin", tmp_path / "ggml-base.en.bin"
    multi.write_bytes(b"x")
    en.write_bytes(b"x")
    return str(binary), str(multi), str(en)


def stt(fake_engine, **kw):
    binary, multi, en = fake_engine
    return WhisperCppSTT(binary, multi, en_model_path=en, **kw)


# ---- language choice ------------------------------------------------------------------------------
@pytest.mark.parametrize("detected,p,expected,uncertain", [
    ("ta", 0.92, "ta", False),
    ("hi", 0.97, "hi", False),
    ("en", 0.99, "en", False),
    ("ur", 0.88, "hi", False),      # spoken Hindi often detected as Urdu → Hindi (Devanagari)
    ("fr", 0.95, "auto", True),     # unsupported language: transcribed as-is and flagged, never relabelled
    ("en", 0.30, "auto", True),     # weak detection: not forced; whisper decodes freely, flagged uncertain
    (None, 0.0, "auto", True),      # detection produced nothing
])
def test_detection_is_restricted_and_flags_uncertainty(fake_engine, monkeypatch, detected, p, expected, uncertain):
    monkeypatch.setenv("FAKE_LANG", detected or "none")
    monkeypatch.setenv("FAKE_P", str(p))
    t = stt(fake_engine).recognize(make_tone(), "audio/wav", "auto")
    assert (t.language, t.uncertain) == (expected, uncertain)
    assert f"lang={expected}" in t.text


def test_english_uses_english_model_and_order_prompt(fake_engine, monkeypatch):
    monkeypatch.setenv("FAKE_LANG", "en")
    t = stt(fake_engine).recognize(make_tone(), "audio/wav", "auto", english_prompt="Order numbers look like SA-10001")
    assert "model=ggml-base.en.bin" in t.text and "prompt=Order numbers" in t.text


def test_tamil_and_hindi_use_multilingual_model_and_native_prompt(fake_engine, monkeypatch):
    for code in ("ta", "hi"):
        monkeypatch.setenv("FAKE_LANG", code)
        t = stt(fake_engine).recognize(make_tone(), "audio/wav", "auto", english_prompt="ENGLISH ONLY")
        assert "model=ggml-base.bin" in t.text and LANGUAGE_PROMPTS[code].split()[0] in t.text and "ENGLISH" not in t.text


def test_explicit_language_skips_detection(fake_engine, monkeypatch):
    monkeypatch.setenv("FAKE_LANG", "en")
    t = stt(fake_engine).recognize(make_tone(), "audio/wav", "hi")
    assert t.language == "hi" and t.detected_language is None and not t.uncertain


def test_detection_off_uses_default(fake_engine, monkeypatch):
    monkeypatch.setenv("FAKE_LANG", "en")
    t = stt(fake_engine, detect=False).recognize(make_tone(), "audio/wav", "auto")
    assert t.language == "ta" and t.detected_language is None


def test_language_outside_configured_set_rejected(fake_engine):
    from app.speech.adapters import SpeechError

    with pytest.raises(SpeechError):
        stt(fake_engine, languages=("ta", "en")).recognize(make_tone(), "audio/wav", "hi")


def test_english_only_model_cannot_offer_tamil(fake_engine):
    binary, _multi, en = fake_engine
    s = WhisperCppSTT(binary, en, languages=("ta", "en", "hi"), default_language="ta")
    assert s.languages == ("en",) and s.default_language == "en" and s.detect is False


# ---- API / config -----------------------------------------------------------------------------------
def test_capabilities_report_tamil_default(client):
    caps = client.get("/api/speech/capabilities").json()
    assert caps["default_voice_language"] == "ta"
    assert [l["code"] for l in caps["voice_languages"]] == ["ta", "en", "hi"]


def test_transcribe_endpoint_reports_language(settings, fake_engine, monkeypatch):
    monkeypatch.setenv("FAKE_LANG", "hi")
    with make_client(settings) as c:
        c.app.state.stt = stt(fake_engine)
        r = c.post("/api/stores/store-a/speech/transcribe?language=auto", content=make_tone(), headers={"Content-Type": "audio/wav"})
        body = r.json()
        assert body["detected_language"] == "hi" and body["uncertain"] is False
        # The receipt binds this server's detection to this exact transcript and store.
        from app.assistant.language import verify_receipt

        key = c.app.state.settings.secret_key
        assert verify_receipt(key, body["speech_receipt"], "store-a", body["text"])[0] == "hi"
        assert verify_receipt(key, body["speech_receipt"], "store-b", body["text"]) is None
        assert verify_receipt(key, body["speech_receipt"], "store-a", body["text"] + " edited") is None
        caps = c.get("/api/speech/capabilities").json()["server_stt"]
        assert caps["language_detection"] is True and caps["default_language"] == "ta" and caps["languages"] == ["ta", "en", "hi"]
        assert c.post("/api/stores/store-a/speech/transcribe?language=fr", content=make_wav(),
                      headers={"Content-Type": "audio/wav"}).status_code == 422


def test_language_config_validation(tmp_path):
    from app.config import ConfigError, load_settings
    from tests.test_platform import GOOD_ENV

    s = load_settings(GOOD_ENV, env_file=tmp_path / "x")
    assert s.speech_default_language == "ta" and s.speech_languages == ("ta", "en", "hi")
    for bad in ({"SPEECH_LANGUAGES": "ta,fr"}, {"SPEECH_LANGUAGES": "en", "SPEECH_DEFAULT_LANGUAGE": "ta"},
                {"SPEECH_LANGUAGE_DETECTION": "maybe"}):
        with pytest.raises(ConfigError):
            load_settings({**GOOD_ENV, **bad}, env_file=tmp_path / "x")


# ---- real engines: macOS voices → whisper.cpp (no physical microphone) ---------------------------------
MULTI = os.environ.get("AVC_TEST_WHISPER_MULTI_MODEL", "")
EN = os.environ.get("AVC_TEST_WHISPER_MODEL", "")
HAS_REAL = bool(shutil.which("whisper-cli") and shutil.which("say") and MULTI and os.path.isfile(MULTI))
PHRASES = [
    ("Vani", "ta", "உங்களிடம் இரண்டு பேர் தங்கும் கூடாரம் இருக்கிறதா?", "஀", "௿"),
    ("Lekha", "hi", "मेरा ऑर्डर कहाँ है?", "ऀ", "ॿ"),
    ("Samantha", "en", "Do you have a two person tent?", "a", "z"),
]


def _voice_wav(tmp_path, voice, text, name):
    aiff, wav = tmp_path / f"{name}.aiff", tmp_path / f"{name}.wav"
    subprocess.run(["say", "-v", voice, "-o", str(aiff), text], check=True)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)], check=True)
    return wav.read_bytes()


@pytest.mark.skipif(not HAS_REAL, reason="set AVC_TEST_WHISPER_MULTI_MODEL to a multilingual ggml model")
@pytest.mark.parametrize("voice,code,text,lo,hi", PHRASES)
def test_real_language_identification(tmp_path, voice, code, text, lo, hi):
    engine = WhisperCppSTT("whisper-cli", MULTI, en_model_path=EN if os.path.isfile(EN) else "")
    t = engine.recognize(_voice_wav(tmp_path, voice, text, code), "audio/wav", "auto")
    assert t.detected_language == code and t.language == code and not t.uncertain, t
    assert t.language_probability >= 0.5
    # Transcript is in the right script.
    letters = [ch for ch in t.text.lower() if ch.isalpha()]
    assert letters and sum(lo <= ch <= hi for ch in letters) / len(letters) > 0.6, t.text


def test_silence_never_becomes_a_question(fake_engine):
    # Found on the real engine: 2 s of silence + the Tamil prompt produced "ஷிப்பிங் கட்டணம் உள்ளது" ("there is a shipping charge").
    t = stt(fake_engine).recognize(make_wav(2.0), "audio/wav", "auto")
    assert t.text == "" and t.detected_language is None


def test_no_vocabulary_prompt_on_fallback(fake_engine, monkeypatch):
    monkeypatch.setenv("FAKE_LANG", "en")
    monkeypatch.setenv("FAKE_P", "0.2")
    t = stt(fake_engine).recognize(make_tone(), "audio/wav", "auto")
    assert t.uncertain and "prompt=no" in t.text


def make_tone(seconds=1.0, rate=16000):
    import io, math, wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"".join(int(8000 * math.sin(2 * math.pi * 220 * i / rate)).to_bytes(2, "little", signed=True)
                               for i in range(int(seconds * rate))))
    return buf.getvalue()


@pytest.mark.skipif(not HAS_REAL, reason="set AVC_TEST_WHISPER_MULTI_MODEL to a multilingual ggml model")
def test_real_silence_and_noise_do_not_invent_text():
    engine = WhisperCppSTT("whisper-cli", MULTI)
    assert engine.recognize(make_wav(2.0), "audio/wav", "auto").text == ""
    hum = engine.recognize(make_tone(2.0), "audio/wav", "auto")
    # Weak detection on a hum is flagged and decoded without forcing a language: measured result is no text at all
    # (previously, forced Tamil decoding produced junk like "-ஜாஜாஜாஜா").
    assert hum.uncertain and hum.text == ""


def test_weak_urdu_detection_is_not_mapped_to_hindi(fake_engine, monkeypatch):
    monkeypatch.setenv("FAKE_LANG", "ur")
    monkeypatch.setenv("FAKE_P", "0.55")
    t = stt(fake_engine).recognize(make_tone(), "audio/wav", "auto")
    assert t.uncertain and t.language == "auto" and t.detected_language == "ur"

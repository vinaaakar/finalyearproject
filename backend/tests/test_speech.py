"""Server-side speech: WAV validation, endpoints, and (when installed) real local engines."""

import io
import os
import shutil
import subprocess
import wave

import pytest

from app.speech.adapters import MacSayTTS, SpeechError, WhisperCppSTT, wav_duration_seconds
from tests.conftest import make_client


def make_wav(seconds=1.0, rate=16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


class FakeSTT:
    name = "fake"
    available = True

    def __init__(self):
        self.calls = []

    def transcribe(self, audio, mime_type, language="en", prompt=None):
        wav_duration_seconds(audio)
        self.calls.append(prompt)
        return "where is my order"


def test_wav_validation():
    assert abs(wav_duration_seconds(make_wav(2.0)) - 2.0) < 0.01
    for bad in (b"", b"not audio at all" * 10, b"RIFF\x00\x00\x00\x00WAVEjunk" + b"\x00" * 40):
        with pytest.raises(SpeechError):
            wav_duration_seconds(bad)


def test_capabilities_off_by_default(client):
    body = client.get("/api/speech/capabilities").json()
    assert body["server_stt"]["available"] is False and body["recommended_client_mode"] == "browser"
    assert client.post("/api/stores/store-a/speech/transcribe", content=make_wav(), headers={"Content-Type": "audio/wav"}).status_code == 503
    assert client.post("/api/speech/synthesize", json={"text": "hi"}).status_code == 503


def test_transcribe_endpoint_with_fake_engine(settings):
    with make_client(settings) as c:
        fake = FakeSTT()
        c.app.state.stt = fake
        r = c.post("/api/stores/store-b/speech/transcribe", content=make_wav(), headers={"Content-Type": "audio/wav"})
        assert r.status_code == 200 and r.json()["text"] == "where is my order"
        assert "BB-10001" in fake.calls[0]  # store-specific order-number hint
        assert c.get("/api/speech/capabilities").json()["recommended_client_mode"] == "server"
        # Oversized uploads are refused before transcription.
        big = c.post("/api/stores/store-b/speech/transcribe", content=b"\x00" * (2 * 1024 * 1024 + 10), headers={"Content-Type": "audio/wav"})
        assert big.status_code == 413
        assert c.post("/api/stores/store-c/speech/transcribe", content=make_wav(), headers={"Content-Type": "audio/wav"}).status_code == 422


def test_whisper_adapter_rejects_bad_input(tmp_path):
    model = tmp_path / "model.bin"
    model.write_bytes(b"x")
    stt = WhisperCppSTT("/bin/echo", str(model))
    with pytest.raises(SpeechError):
        stt.transcribe(b"garbage", "audio/wav")
    with pytest.raises(SpeechError):
        stt.transcribe(make_wav(), "audio/webm")
    with pytest.raises(SpeechError):
        stt.transcribe(make_wav(31), "audio/wav")


def test_config_requires_model_for_whisper(tmp_path):
    from app.config import ConfigError, load_settings
    from tests.test_platform import GOOD_ENV

    with pytest.raises(ConfigError) as exc:
        load_settings({**GOOD_ENV, "SPEECH_STT": "whisper_cpp", "WHISPER_MODEL_PATH": str(tmp_path / "missing.bin")}, env_file=tmp_path / "x")
    assert "WHISPER_MODEL_PATH" in str(exc.value)
    with pytest.raises(ConfigError):
        load_settings({**GOOD_ENV, "TTS_VOICE": "-o /etc/passwd"}, env_file=tmp_path / "x")


# ---- real local engines (skipped when not installed) ------------------------------------------
HAS_SAY = bool(shutil.which("say") and shutil.which("afconvert"))
WHISPER_MODEL = os.environ.get("AVC_TEST_WHISPER_MODEL", "")
HAS_WHISPER = bool(shutil.which("whisper-cli") and WHISPER_MODEL and os.path.isfile(WHISPER_MODEL))


@pytest.mark.skipif(not HAS_SAY, reason="macOS say/afconvert not available")
def test_macos_say_produces_wav():
    audio, mime = MacSayTTS().synthesize("Your order is on its way.")
    assert mime == "audio/wav" and wav_duration_seconds(audio) > 0.5


@pytest.mark.skipif(not HAS_SAY, reason="macOS say/afconvert not available")
def test_say_text_cannot_inject_options():
    # Text that looks like command-line options is spoken, not interpreted.
    audio, _ = MacSayTTS().synthesize("-o /tmp/pwned.aiff --help")
    assert wav_duration_seconds(audio) > 0.3 and not os.path.exists("/tmp/pwned.aiff")


@pytest.mark.skipif(not (HAS_SAY and HAS_WHISPER), reason="set AVC_TEST_WHISPER_MODEL and install whisper-cli")
def test_real_round_trip_say_then_whisper(tmp_path):
    aiff, wav = tmp_path / "q.aiff", tmp_path / "q.wav"
    subprocess.run(["say", "-v", "Samantha", "-o", str(aiff), "Where is my order S A one zero zero zero one?"], check=True)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)], check=True)
    text = WhisperCppSTT("whisper-cli", WHISPER_MODEL).transcribe(wav.read_bytes(), "audio/wav",
                                                                    prompt="Order numbers look like SA-10001: two letters, a dash, five digits.")
    assert "SA-10001" in text

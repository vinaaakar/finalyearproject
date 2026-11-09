"""Server-side speech adapters.

Browser speech (Web Speech API, see frontend/packages/shared/src/voice.js) always works as a
fallback. These adapters add fully LOCAL engines that run on this machine:

- WhisperCppSTT: speech-to-text with whisper.cpp's `whisper-cli` and a ggml model file. With a
                 multilingual model it identifies the spoken language (restricted to the configured
                 languages, Tamil by default) and then transcribes in that language.
- MacSayTTS:     text-to-speech with macOS's built-in `say` (+ `afconvert` to WAV).

Both are off unless configured (SPEECH_STT / SPEECH_TTS). Audio is written only to private
temporary files that are deleted immediately, and is never logged or stored.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 2 * 1024 * 1024   # ≈ 60 s of 16 kHz 16-bit mono
MAX_AUDIO_SECONDS = 30
MAX_TTS_CHARS = 1000

SUPPORTED_LANGUAGES = {"ta": "Tamil", "en": "English", "hi": "Hindi"}
# Whisper often labels spoken Hindi as Urdu (the spoken languages are nearly identical);
# when Hindi is allowed and Urdu is not, treat "ur" as Hindi so the transcript uses Devanagari.
LANGUAGE_ALIASES = {"ur": "hi"}
# Native-script vocabulary hints (no product names, so they suit every store). Measured on this Mac with
# ggml-base: they keep Hindi in Devanagari instead of Urdu script and improve Tamil spelling.
LANGUAGE_PROMPTS = {
    "ta": "என் ஆர்டர் எங்கே? இது ஸ்டாக்கில் உள்ளதா? ஷிப்பிங் கட்டணம் எவ்வளவு? திருப்பி அனுப்பலாமா?",
    "hi": "मेरा ऑर्डर कहाँ है? क्या यह स्टॉक में है? शिपिंग कितनी है? क्या मैं इसे वापस कर सकता हूँ?",
}
_DETECTED_RE = re.compile(r"auto-detected language: ([a-z]{2,3}) \(p = ([0-9.]+)\)")


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str                     # language the transcript was produced in ("auto" if left to whisper)
    detected_language: str | None     # what auto-detection reported, after aliases (None if not run)
    language_probability: float | None
    uncertain: bool                   # detection was weak or found an unsupported language


class SpeechError(Exception):
    """Raised with a message that is safe to show to the user."""


class SpeechToText(Protocol):
    name: str
    available: bool

    def transcribe(self, audio: bytes, mime_type: str, language: str = "en", prompt: str | None = None) -> str: ...


class TextToSpeech(Protocol):
    name: str
    available: bool

    def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]: ...


class NotConfiguredSTT:
    name = "none"
    available = False

    def transcribe(self, audio: bytes, mime_type: str, language: str = "en", prompt: str | None = None) -> str:
        raise SpeechError("Server speech recognition is not configured.")


class NotConfiguredTTS:
    name = "none"
    available = False

    def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
        raise SpeechError("Server text-to-speech is not configured.")


def wav_duration_seconds(audio: bytes) -> float:
    """Validate a PCM WAV file and return its duration. Only plain RIFF/WAVE PCM is accepted."""
    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise SpeechError("Audio must be a WAV file.")
    pos, fmt, data_len = 12, None, None
    while pos + 8 <= len(audio):
        chunk, size = audio[pos:pos + 4], struct.unpack("<I", audio[pos + 4:pos + 8])[0]
        if chunk == b"fmt " and size >= 16:
            fmt = struct.unpack("<HHIIHH", audio[pos + 8:pos + 24])
        elif chunk == b"data":
            data_len = min(size, len(audio) - pos - 8)
            break
        pos += 8 + size + (size & 1)
    if fmt is None or data_len is None:
        raise SpeechError("Audio must be a WAV file.")
    audio_format, channels, rate, byte_rate, _align, bits = fmt
    if audio_format != 1 or channels not in (1, 2) or bits != 16 or not 8000 <= rate <= 48000 or byte_rate == 0:
        raise SpeechError("Audio must be 16-bit PCM WAV.")
    return data_len / byte_rate


SILENCE_RMS = 0.004  # ≈ -48 dBFS; below this a recording is treated as silence


def wav_rms(audio: bytes) -> float:
    """Root-mean-square level (0..1) of a 16-bit PCM WAV's data chunk (already validated)."""
    import array
    import math

    start = audio.find(b"data") + 8
    samples = array.array("h", audio[start:start + ((len(audio) - start) // 2) * 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(x * x for x in samples) / len(samples)) / 32768


def is_english_only_model(path: str) -> bool:
    """whisper.cpp English-only models are named like ggml-base.en.bin / ggml-small.en-q5_1.bin."""
    return ".en" in Path(path).name


class WhisperCppSTT:
    name = "whisper.cpp"

    def __init__(self, binary: str, model_path: str, threads: int = 4, timeout: float = 30.0, *,
                 en_model_path: str = "", languages: tuple[str, ...] = ("ta", "en", "hi"), default_language: str = "ta",
                 detect: bool = True, min_confidence: float = 0.5):
        self.binary = shutil.which(binary) or binary
        self.model_path = model_path
        self.en_model_path = en_model_path
        self.threads = threads
        self.timeout = timeout
        self.min_confidence = min_confidence
        if is_english_only_model(model_path):
            # An English-only model cannot recognise or identify other languages.
            self.languages, self.default_language, self.detect = ("en",), "en", False
        else:
            self.languages, self.default_language, self.detect = tuple(languages), default_language, detect

    @property
    def available(self) -> bool:
        return bool(self.model_path) and Path(self.model_path).is_file() and Path(self.binary).is_file() and os.access(self.binary, os.X_OK)

    @property
    def multilingual(self) -> bool:
        return not is_english_only_model(self.model_path)

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        try:
            out = subprocess.run([self.binary, "-t", str(self.threads), *args], capture_output=True, text=True, timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired:
            raise SpeechError("Speech recognition took too long. Please try again.")
        if out.returncode != 0:
            log.warning("whisper.cpp failed with exit code %s", out.returncode)
            raise SpeechError("Speech recognition failed. Please try again or type your question.")
        return out

    def _detect(self, wav: Path) -> tuple[str | None, float]:
        out = self._run(["-m", self.model_path, "-f", str(wav), "-l", "auto", "-dl"])
        m = _DETECTED_RE.search(out.stderr + out.stdout)
        return (m.group(1), float(m.group(2))) if m else (None, 0.0)

    def choose_language(self, detected: str | None, probability: float) -> tuple[str, bool]:
        """Returns (transcription language, uncertain). Restricted to the configured languages.
        Only a CONFIDENT supported detection fixes the transcription language. A weak, unsupported or missing
        detection is transcribed with whisper's own auto mode (never forced), so the script of the transcript
        is independent evidence for the text-based check in assistant/language.py."""
        if detected in self.languages and probability >= self.min_confidence:
            return detected, False
        return "auto", True

    def recognize(self, audio: bytes, mime_type: str, language: str | None = "auto", english_prompt: str | None = None) -> Transcript:
        if not self.available:
            raise SpeechError("Server speech recognition is not available.")
        if mime_type not in ("audio/wav", "audio/x-wav", "audio/wave"):
            raise SpeechError("Audio must be a WAV file.")
        if len(audio) > MAX_AUDIO_BYTES:
            raise SpeechError("That recording is too long.")
        if wav_duration_seconds(audio) > MAX_AUDIO_SECONDS:
            raise SpeechError("That recording is too long.")
        if language not in (None, "auto") and language not in self.languages:
            raise SpeechError("That voice language is not available.")
        if wav_rms(audio) < SILENCE_RMS:
            # Whisper invents sentences for silence (especially with a prompt); never send those as a question.
            return Transcript("", language if language not in (None, "auto") else "auto", None, None, False)
        with tempfile.TemporaryDirectory(prefix="avc-stt-") as tmp:
            path = Path(tmp) / "input.wav"
            path.write_bytes(audio)
            os.chmod(path, 0o600)
            detected, probability = None, None
            if language not in (None, "auto"):
                lang, uncertain = language, False                     # explicit override (not detection)
            elif self.detect and len(self.languages) > 1:
                raw, probability = self._detect(path)
                aliased = raw not in self.languages and LANGUAGE_ALIASES.get(raw) in self.languages
                detected = LANGUAGE_ALIASES[raw] if aliased else raw
                lang, uncertain = self.choose_language(detected, probability)
                if aliased and (probability or 0) < 0.75:
                    # A weak "Urdu" is as likely to be a misheard Tamil clip as Hindi (observed): don't map it.
                    detected, lang, uncertain = raw, "auto", True
            else:
                lang, uncertain = self.default_language, False        # detection off: configured default
            # English goes to the dedicated English model when one is configured (more accurate).
            model = self.en_model_path if lang == "en" and self.en_model_path and Path(self.en_model_path).is_file() else self.model_path
            # Vocabulary prompts only when the language is known; on uncertain audio they encourage hallucination.
            prompt = None if uncertain else english_prompt if lang == "en" else LANGUAGE_PROMPTS.get(lang)
            args = ["-m", model, "-f", str(path), "-l", lang, "-nt", "-np"] + (["--prompt", prompt] if prompt else [])
            out = self._run(args)
        text = " ".join(out.stdout.split())
        # whisper emits markers like [BLANK_AUDIO] for silence.
        if text.startswith("[") and text.endswith("]"):
            text = ""
        return Transcript(text, lang, detected, probability, uncertain)

    def transcribe(self, audio: bytes, mime_type: str, language: str = "en", prompt: str | None = None) -> str:
        return self.recognize(audio, mime_type, language, english_prompt=prompt).text


class MacSayTTS:
    name = "macos-say"

    def __init__(self, voice: str = "Samantha", timeout: float = 20.0, language_voices: dict[str, str] | None = None):
        self.voice = voice
        self.timeout = timeout
        # One installed macOS voice per supported language (Vani = ta_IN, Lekha = hi_IN on this Mac).
        self.language_voices = {"en": voice, **(language_voices or {"ta": "Vani", "hi": "Lekha"})}
        self._installed: dict[str, str] | None = None

    @property
    def available(self) -> bool:
        return bool(shutil.which("say") and shutil.which("afconvert"))

    def installed_voices(self) -> dict[str, str]:
        """name → locale for the voices macOS actually has (`say -v ?`)."""
        if self._installed is None:
            out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10).stdout if self.available else ""
            self._installed = {}
            for line in out.splitlines():
                m = re.match(r"^(.+?)\s+([a-z]{2}_[A-Z]{2})\s+#", line)
                if m:
                    self._installed[m.group(1).strip()] = m.group(2)
        return self._installed

    def voice_for(self, language: str) -> str | None:
        """The configured voice for this language if it is installed AND matches the language; else None."""
        name = self.language_voices.get(language)
        locale = self.installed_voices().get(name or "")
        return name if locale and locale.startswith(language + "_") else None

    def languages(self) -> dict[str, str | None]:
        return {lang: self.voice_for(lang) for lang in SUPPORTED_LANGUAGES}

    def synthesize(self, text: str, voice: str | None = None, language: str | None = None) -> tuple[bytes, str]:
        if not self.available:
            raise SpeechError("Server text-to-speech is not available.")
        if language:
            voice = self.voice_for(language)
            if voice is None:
                raise SpeechError(f"No {SUPPORTED_LANGUAGES.get(language, language)} voice is installed for server speech.")
        text = " ".join(text.split())[:MAX_TTS_CHARS]
        if not text:
            raise SpeechError("Nothing to say.")
        with tempfile.TemporaryDirectory(prefix="avc-tts-") as tmp:
            src, aiff, wav = Path(tmp) / "in.txt", Path(tmp) / "out.aiff", Path(tmp) / "out.wav"
            # Text goes through a file (never argv), so it cannot be parsed as command-line options.
            src.write_text(text)
            try:
                subprocess.run(["say", "-v", voice or self.voice, "-o", str(aiff), "-f", str(src)], check=True, capture_output=True, timeout=self.timeout)
                subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@22050", "-c", "1", str(aiff), str(wav)], check=True,
                               capture_output=True, timeout=self.timeout)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                log.warning("macOS say/afconvert failed")
                raise SpeechError("Text-to-speech failed.")
            return wav.read_bytes(), "audio/wav"


def build_stt(kind: str, binary: str, model_path: str, *, en_model_path: str = "", languages: tuple[str, ...] = ("ta", "en", "hi"),
              default_language: str = "ta", detect: bool = True) -> SpeechToText:
    if kind != "whisper_cpp":
        return NotConfiguredSTT()
    return WhisperCppSTT(binary, model_path, en_model_path=en_model_path, languages=languages, default_language=default_language, detect=detect)


def build_tts(kind: str, voice: str, language_voices: dict[str, str] | None = None) -> TextToSpeech:
    return MacSayTTS(voice, language_voices=language_voices) if kind == "macos_say" else NotConfiguredTTS()


def capabilities(stt: SpeechToText, tts: TextToSpeech, languages: tuple[str, ...] = ("ta", "en", "hi"), default_language: str = "ta") -> dict:
    server_langs = getattr(stt, "languages", None) if stt.available else None
    return {
        "server_stt": {
            "available": stt.available, "engine": stt.name, "local": stt.available,
            "languages": list(server_langs) if server_langs else [],
            "language_detection": bool(stt.available and getattr(stt, "detect", False) and server_langs and len(server_langs) > 1),
            "default_language": getattr(stt, "default_language", None) if stt.available else None,
        },
        "server_tts": {"available": tts.available, "engine": tts.name, "local": tts.available,
                       # language → installed voice name, or null when no matching voice exists
                       "voices": tts.languages() if tts.available and hasattr(tts, "languages") else {}},
        "recommended_client_mode": "server" if stt.available else "browser",
        # Voice-input languages offered to the browser recognizer (which cannot auto-detect).
        "voice_languages": [{"code": c, "name": SUPPORTED_LANGUAGES[c]} for c in languages],
        "default_voice_language": default_language,
    }

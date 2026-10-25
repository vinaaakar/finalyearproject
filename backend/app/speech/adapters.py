"""Server-side speech adapter slots.

Milestone 3 ships browser-based speech (see frontend/packages/shared/src/voice.js).
These interfaces let a local engine (e.g. whisper.cpp / faster-whisper for STT,
Piper for TTS) be plugged in later without changing the chat or phone flows.
No engine is installed by default, so both report `available: False`.
"""

from __future__ import annotations

from typing import Protocol


class SpeechToText(Protocol):
    name: str
    available: bool

    def transcribe(self, audio: bytes, mime_type: str, language: str = "en") -> str: ...


class TextToSpeech(Protocol):
    name: str
    available: bool

    def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]: ...


class NotConfiguredSTT:
    name = "none"
    available = False

    def transcribe(self, audio: bytes, mime_type: str, language: str = "en") -> str:
        raise NotImplementedError("No server-side speech-to-text engine is configured")


class NotConfiguredTTS:
    name = "none"
    available = False

    def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
        raise NotImplementedError("No server-side text-to-speech engine is configured")


def capabilities(stt: SpeechToText, tts: TextToSpeech) -> dict:
    return {
        "server_stt": {"available": stt.available, "engine": stt.name},
        "server_tts": {"available": tts.available, "engine": tts.name},
        "recommended_client_mode": "browser" if not stt.available else "server",
    }

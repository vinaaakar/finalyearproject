# Voice interface

## Current implementation (browser)

`frontend/packages/shared/src/voice.js`

| Piece | Technology | Where audio is processed |
|---|---|---|
| Speech-to-text | Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`) | Chrome/Edge: the vendor's cloud service. Safari: on-device or Apple servers, depending on OS settings. Firefox: not supported, so typing is the fallback. |
| Text-to-speech | `speechSynthesis` | Local OS voices |

Error handling: microphone permission denied, no microphone, no speech heard, network failure,
unsupported browser and non-secure origin all show a plain-language message in the chat widget.
Typing always keeps working.

## Adding fully local speech-to-text (not installed)

The backend exposes adapter slots in `backend/app/speech/adapters.py` and reports them through
`GET /api/speech/capabilities`. To process audio locally:

1. Pick an engine:
   - **whisper.cpp** with the `base.en` model: about 150 MB, runs on the M4 GPU.
   - **faster-whisper** `small`: about 500 MB, plus about 100 MB of Python packages.
2. Implement the `SpeechToText` protocol, set `app.state.stt` to it in `main.py`, and add a
   `POST /api/speech/transcribe` route. That route needs the `python-multipart` package to receive uploads.
3. In `voice.js`, add a server recognizer: record with `MediaRecorder`, POST the blob, and treat the
   response as the final transcript. `selectRecognizer()` should pick it when
   `server_stt.available` is true.

Check free disk space before downloading models. These are not needed for the current milestone.

## Adding local neural text-to-speech (optional)

**Piper** voices are about 20–60 MB each. Implement `TextToSpeech.synthesize()` so it returns WAV
bytes, and play them in the browser instead of using `speechSynthesis`.

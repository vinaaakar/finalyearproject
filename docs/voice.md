# Voice and languages

The chat assistant (Scout for Summit Trail Co., Maple for Bloom & Brew) supports exactly three
languages: **Tamil (ta-IN, default)**, **English (en-IN)** and **Hindi (hi-IN)**. The language of every
message is identified from what the customer actually said, and the reply, both text and speech, uses that
language. Typing always works too.

## Behaviour

| Situation | What happens |
|---|---|
| New conversation | The chat widget opens in Tamil: welcome text, suggestion chips, placeholders, mic messages and the selector. |
| Customer speaks or types Tamil / English / Hindi | The language is identified **for that utterance**, and the reply and its speech use it. |
| Customer switches language mid-conversation | The next utterance is identified on its own merits, and the conversation follows (tested ta → en → hi → ta). |
| Language-neutral message (e.g. just `SA-10001`, `ok`, a product name) | The reply uses the **current conversation language** and is labelled "language not detected". It is never shown as detected. |
| Identification uncertain (weak/conflicting evidence, or an unsupported language such as Telugu) | A short clarification in the conversation language, with தமிழ் / English / हिन्दी buttons. Choosing one re-transcribes the same recording in that language. The reply is labelled "your choice", not "detected". |
| Selector changed by the customer | An explicit choice: it switches the widget text, and it decides language-neutral messages and clarifications. It is **not** used as detection evidence. |

Each assistant bubble says how its language was chosen: *detected from your words*, *language not
detected, replying in the conversation language*, or *your choice*. The conversation language is kept per
store in `sessionStorage`, so Store A and Store B are independent and a new tab starts in Tamil.

## How identification works

```
mic ─▶ in-page recorder (16 kHz WAV) ─▶ POST /api/stores/{store}/speech/transcribe?language=auto
          whisper.cpp, multilingual model:
            1. detect language (-dl): top-1 over ~99 languages + probability
            2. restrict to {ta, en, hi}: supported + p ≥ 0.5 → transcribe in it;
               weak / unsupported → flag "uncertain" and decode with whisper's own auto mode (never
               forced), so the transcript's script is independent evidence (weak "ur" is NOT mapped to Hindi)
            3. transcribe with that language (English via ggml-base.en if configured)
          ◀─ { text, detected_language, language_probability, uncertain, speech_receipt }
POST /chat { message, conversation_language, speech_receipt }
          backend/app/assistant/language.py — identify(text, acoustic):
            text evidence: script of each word (Tamil / Devanagari / Latin), romanized Tamil/Hindi
            function words ("enga", "irukku", "kya", "hai"…), identifiers ignored, native script dominates
            mixed sentences (≥ 30 % of words); Urdu script is weak Hindi evidence only
            acoustic evidence: used only from a receipt HMAC-signed by this server for this exact text
            and store (a client cannot claim a language)
          → detected | neutral | uncertain → reply language
```

Typed messages use the same text identification without acoustic evidence.

**Why two signals:** the acoustic detector alone confuses short Tamil clips with Telugu, and spoken Hindi
with Urdu. Text alone can't judge a one-word or identifier-only utterance. Each signal can veto
a weak decision by the other, and anything still unclear produces a clarification, not a guess.

## Engine, models and where audio goes

| Piece | What is used | Where it runs |
|---|---|---|
| Speech-to-text + language ID | **whisper.cpp 1.9.5** (`whisper-cli`, Homebrew), **multilingual `ggml-base.bin` (148 MB)**; English transcripts via `ggml-base.en.bin` (148 MB) | On this Mac. Audio goes only to the store's own backend, in temp files deleted immediately. **Audio does not leave the device.** |
| Browser fallback STT (when the local engine is off) | Web Speech API, **one fixed locale** (the conversation language, Tamil by default). It **cannot** identify the language; the UI says so. The transcript still gets text identification. | Chrome/Edge send audio to the browser vendor (Google). This path only applies when local STT is not configured. |
| Speech output | Browser `speechSynthesis` with a **local** voice matching the reply language: **Vani (ta-IN), Lekha (hi-IN), Rishi (en-IN)** on this Mac. Remote voices (e.g. "Google हिन्दी") are never selected. | Local (macOS voices) |
| Speech output fallback | Store server macOS `say` with Vani / Lekha / Rishi (`POST /api/speech/synthesize {text, language}`) | Local |
| No matching voice anywhere | Text only, with a notice ("No Tamil voice is available on this device…"). Nothing is spoken in a wrong-language voice. | — |

Voices actually present (checked in Chrome on this Mac): `ta-IN Vani (local)`, `hi-IN Lekha (local)`,
`en-IN Rishi (local)`, `hi-IN Google हिन्दी (REMOTE, excluded)`. In Chrome the macOS voices appear a moment
*after* the first remote-only list, so the speaker waits for `voiceschanged` before deciding.

**Model location caveat.** No model was downloaded. The multilingual `ggml-base.bin` used for testing is the copy
inside another app's container (`~/Library/Containers/maccatalyst.com.frontrow.vlog/…/whisper_base_v1.bundle/`),
read-only. That app could remove it, so for regular use keep a dedicated copy (148 MB) or a better model.

## Replies in Tamil and Hindi

- Tamil and Hindi replies come from reviewed templates (`backend/app/assistant/i18n.py`) and translated store
  policies (`backend/app/policy_translations.py`, migration `0003`). They are **never** produced by the local LLM:
  `llama3.2:3b` drifts and garbles Tamil, as observed in testing.
- Product names, prices, order numbers, carriers, tracking numbers and dates are inserted verbatim (tested
  identical across all three languages). Category names and order statuses are translated.
- English replies may be phrased by the LLM. The backend rejects any model reply containing Tamil/Devanagari/Arabic
  script, invented prices, order numbers or the other store's name, and falls back to the deterministic English
  answer. Only English history turns are sent to the model.
- Order and cart answers stay deterministic in every language. Authentication, sessions, store isolation and
  prompt-injection protections are unchanged; a language result or override changes words only, never access (tested).

## Enabling on this Mac

**Status: enabled in this machine's dev `.env`** (appended 8 speech settings; models referenced in place, nothing copied).
`GET /api/speech/capabilities` on :8000 reports whisper.cpp with `language_detection: true`, default `ta`.
The settings, for reference:

```
SPEECH_STT=whisper_cpp
WHISPER_MODEL_PATH=/absolute/path/to/ggml-base.bin            # MULTILINGUAL (required for ta/hi)
WHISPER_EN_MODEL_PATH=/Users/<you>/.baymax/models/ggml-base.en.bin   # optional, better English
SPEECH_TTS=macos_say
TTS_VOICE=Rishi            # English voice (en-IN); TTS_VOICE_TA=Vani and TTS_VOICE_HI=Lekha are the defaults
# SPEECH_DEFAULT_LANGUAGE=ta   SPEECH_LANGUAGES=ta,en,hi   SPEECH_LANGUAGE_DETECTION=auto   (defaults)
```

An English-only model (`*.en.bin`) as `WHISPER_MODEL_PATH` disables Tamil/Hindi recognition and detection.
Capabilities then report English only.

## Measured results (this Mac, whisper.cpp + ggml-base)

Engine level (macOS voices → `/speech/transcribe` → `/chat`, `tests/test_multilingual.py`):

| Utterance | Whisper top-1 (p) | Result |
|---|---|---|
| Tamil: "உங்களிடம் இரண்டு பேர் தங்கும் கூடாரம் இருக்கிறதா?" | ta (0.82) | Tamil ✔ |
| English: "What is your return policy?" | en (1.00) | English ✔ |
| Hindi: "मेरा ऑर्डर कहाँ है?" | hi (0.98) | Hindi ✔ |
| Tamil: "திருப்பி அனுப்பும் கொள்கை என்ன?" | ta (0.49) | Tamil ✔ |
| Tamil (short): "ஷிப்பிங் கட்டணம் எவ்வளவு?" | **te (0.54)** | clarification ✔ (no wrong guess); explicit "தமிழ்" retry → correct Tamil answer |

Browser (headless Chrome; macOS-voice WAVs injected through a `getUserMedia` override, then the real recorder and
whisper.cpp): Tamil → English → Hindi → Tamil identified and spoken with Vani / Rishi / Lekha / Vani. The short
Tamil clip (heard as Telugu, p 0.49) produced the clarification, and the தமிழ் button gave the right answer.
A Hindi clip through **Chrome's fake microphone device** was answered in Hindi and spoken with Lekha.

Transcription accuracy with `base` is moderate: Hindi showed small spelling errors (`और्डर` for `ऑर्डर`), and Tamil
had occasional one-letter errors ("ஏன்" for "என்"). Spoken order numbers in Tamil come out as number words and are
lost, so **typing order numbers is recommended**.

## Demonstration: one continuous spoken conversation (dev app, :5180)

The mic was pressed four times, with **no language selection and no reload**. Audio came from a **substitute
microphone**: `getUserMedia` returned a live stream of macOS-voice recordings. Everything after that ran in the real
product: recorder, silence detection, `/speech/transcribe`, whisper.cpp, `/chat`, speech.

| Turn | Customer said | whisper.cpp heard | Detected (p) | Reply | Spoken by |
|---|---|---|---|---|---|
| 1 | உங்களிடம் இரண்டு பேர் தங்கும் கூடாரம் இருக்கிறதா? | உங்களிடம் 20 பெயர் தங்கும் கூடாரம் இருக்கிறதா? | ta (0.83) | Tamil: tents with prices and stock | Vani |
| 2 | What is your return policy? | What is your return policy? | en (1.00) | English: 60-day policy | Rishi |
| 3 | मेरा ऑर्डर कहाँ है? | मेरा और कहा है? | hi (0.97) | Hindi, but a generic help reply ("ऑर्डर" was misheard) | Lekha |
| 4 | திருப்பி அனுப்பும் கொள்கை என்ன? | திருப்பி அனுப்பும் கொள்ளை என்ன? | ta (0.49, weak → decoded freely, Tamil script confirmed) | Tamil: 60-day policy | Vani |

Through **Chrome's fake microphone device** (`--use-file-for-fake-audio-capture`), one launch per utterance. The device
restarts its file on every mic open, so it cannot play a multi-turn conversation. Results: Tamil ta 0.82 ✔, English
en 1.00 ✔, Hindi hi 0.97 ✔ (heard "और्डर"; that spelling is now recognised as "order"). The second Tamil clip was
detected as **Malayalam, p 0.35 (weak)**. Whisper's free decoding wrote Tamil script, so the reply was Tamil, but
the acoustic top-1 was wrong. Re-encoding through Chrome's audio path changes these borderline scores.

## Limitations and what still needs a person

- **Not tested with a physical microphone or a real human voice**, and not with Indian-accented speakers.
  All audio was synthesised with macOS voices. Please try Tamil, English and Hindi with your own voice.
- `whisper-cli` exposes only the top-1 language, so restricted identification can't compare Tamil vs Telugu
  probabilities directly. Short Tamil clips may need a clarification. A bigger model helps:
  `ggml-small.bin` ≈ 466 MB, or quantised `ggml-small-q5_1.bin` ≈ 190 MB. **Not downloaded**: free disk is about
  1 GB, and about 960 MB of that is held by throwaway test-browser profiles awaiting your decision.
- Romanized Tamil/Hindi is recognised in **typed** text (a function-word list). Whisper usually writes native script,
  so romanized output from speech is uncommon.
- Mixed-language policy: native script wins when it makes up ≥ 30 % of the words. Code-switched English nouns are
  kept as spoken, and replies are in the dominant language.
- The phone simulator remains English-only and simulated.
- Only the chat widget is localised. The rest of the storefront pages remain English.

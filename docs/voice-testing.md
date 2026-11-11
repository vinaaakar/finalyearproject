# Voice testing (Phase H)

How to verify Scout and Maple's speech recognition and spoken replies in Tamil (default), English and Hindi, what has
been measured, and what still needs people. Engine details: `docs/voice.md`.

**No physical-microphone test has been performed by the AI assistant that implemented Phase H** (it has no microphone).
Everything below marked *measured* used synthetic macOS-voice audio or recorded files; the microphone procedure in §2 is
for a person to run.

## 1. Local models (project-owned)

`scripts/setup_speech_models.sh --multilingual <ggml-base.bin> [--english <ggml-base.en.bin>]` copies whisper.cpp models
into `models/whisper/` (git-ignored) **only if each file's SHA-1 matches the one published by whisper.cpp**; it never
downloads. Done on this Mac: `ggml-base.bin` (`465707469ff3…`) and `ggml-base.en.bin` (`137c40403d78…`), 296 MB in
total. When `WHISPER_MODEL_PATH` / `WHISPER_EN_MODEL_PATH` are unset, the backend uses these copies (the development
configuration does this since 2026-11-11).

## 2. Physical microphone workflow (for a person)

Equipment: the Mac's built-in microphone, plus a headset if available. Chrome, dev storefront on 5180 / 5181 with
`SPEECH_STT=whisper_cpp`.

1. **Permission and errors:** open the chat and press 🎤. Deny the permission once: the notice must say the microphone
   is blocked (in the conversation language). Allow it and continue. Unplug the headset mid-session: the next press
   must say no microphone was found, or use the built-in one.
2. **Default language:** a new tab opens in Tamil. Say each phrase below once, in a quiet room, at a normal distance:

   | Language | Phrase | Expected answer |
   |---|---|---|
   | Tamil | உங்களிடம் இரண்டு பேர் தங்கும் கூடாரம் இருக்கிறதா? | Tamil, tents with prices and stock |
   | Tamil | திருப்பி அனுப்பும் கொள்கை என்ன? | Tamil, return policy |
   | English | What is your return policy? | English |
   | Hindi | मेरा ऑर्डर कहाँ है? | Hindi, asks to sign in (or the order status if signed in) |
   | Hindi | आपकी वापसी नीति क्या है? | Hindi, return policy |

3. **Switching:** in one conversation, say Tamil → English → Hindi → Tamil without touching the language menu. Each reply
   must be in the language just spoken (or a clarification offering the three languages — never a wrong-language
   answer).
4. **Interruption:** while a long reply is being spoken, press 🎤: the speech must stop immediately and recording must
   start. While a reply is being spoken, type and send a question: the old speech must stop. Close the chat while it
   is speaking: it must stop.
5. **Cancellation and timeouts:** press 🎤 and say nothing: after about 6 s, “I didn’t hear anything”. Keep talking:
   recording stops by itself at 15 s. Press 🎤 and close the chat while recording: nothing is sent.
6. **Realistic conditions:** repeat step 2 with (a) a fan or street noise, (b) 2 m from the laptop, (c) a headset,
   (d) speaking quickly. Note every misheard phrase.
7. **Record for scoring:** record each phrase as a file (QuickTime Player → New Audio Recording, or Voice Memos →
   share as M4A) and score it — §3.

## 3. Scoring recordings (and native-speaker review)

Put the files in one folder with a `manifest.csv`:

```
file,language,expected_text,speaker,conditions
ta_tent_quiet.m4a,ta,உங்களிடம் இரண்டு பேர் தங்கும் கூடாரம் இருக்கிறதா?,native-ta-1,quiet / built-in mic
hi_order_fan.m4a,hi,मेरा ऑर्डर कहाँ है?,native-hi-1,fan noise / 1 m
```

`backend/.venv/bin/python scripts/voice_eval.py --recordings <folder> --json results.json` runs every file through the
same engine the stores use and reports, per language and condition: language correct, how often it asked for
clarification, **wrong-language answers (must be 0)**, and the character error rate against the expected text.
Recordings stay on this Mac.

**Native-speaker review (not yet arranged).** Ask at least two native Tamil and two native Hindi speakers to (1) record
the phrases (§2 step 7, plus their own natural questions about tents, coffee, orders and returns) and (2) read the
assistant's Tamil and Hindi replies, the policy translations (`backend/app/policy_translations.py`) and the new Phase A
message (`assistant/care_text.py` → `business_info`), marking anything unnatural or wrong.

## 4. Measured (synthetic) — `scripts/voice_eval.py --synthetic --snr 20 10 5`

macOS voices Vani (ta), Rishi (en), Lekha (hi), 4 phrases each, clean and with white noise at 20 / 10 / 5 dB SNR,
whisper.cpp + multilingual `ggml-base` on this Mac (31 s for 48 recognitions):

| Language | Condition | Language correct | Asked to clarify | Wrong-language answer | Character error rate |
|---|---|---|---|---|---|
| English | clean / 20 dB / 10 dB / 5 dB | 4 / 4 / 4 / 4 of 4 | 0 | **0** | 0.00 / 0.00 / 0.00 / 0.07 |
| Hindi | clean / 20 dB / 10 dB / 5 dB | 4 / 4 / 3 / 2 | 0 / 0 / 1 / 2 | **0** | 0.21 / 0.19 / 0.68 / 0.85 |
| Tamil | clean / 20 dB / 10 dB / 5 dB | 2 / 2 / 1 / 1 | 2 / 2 / 3 / 3 | **0** | 0.30 / 0.31 / 0.65 / 0.70 |

Reading: the safety property holds — **no utterance was ever answered in the wrong language**; weak detections become a
clarification. Recognition quality with the `base` model is good for English, fair for Hindi and weak for Tamil, and
drops sharply in noise. A larger multilingual model (`ggml-small.bin` ≈ 466 MB, `ggml-medium.bin` ≈ 1.5 GB) is the usual
remedy; it was **not downloaded** (needs your approval; 13 GB free) and would need re-measuring here.

## 5. Automated coverage

* Backend (`tests/test_speech*.py`, `test_multilingual.py`): limits, WAV validation, engine timeouts, language choice,
  clarification flow, receipts, privacy; with `AVC_TEST_WHISPER_MULTI_MODEL` / `AVC_TEST_WHISPER_MODEL` set to the project
  models, the 7 real-engine tests run too (79 passed, 0 skipped on this Mac).
* Frontend (`packages/shared/src/__tests__/voice.test.js`, 16 tests): end of speech after silence, 16 kHz WAV, 6 s
  no-speech, 15 s cap, cancel discards the recording, microphone permission / device errors, **transcription timeout**
  (new: 45 s), local-only voice choice (remote voices never used, no wrong-language voice), **interruption**: a reply
  cancelled while voices or server audio are still loading is never spoken (new; previously it could start after the
  customer pressed the mic or closed the chat), and sending a typed message stops a reply being read aloud.
* Relevance (`tests/test_phaseH_relevance.py`): needs (“keep me warm”) → sleeping bag; party size (“tent for 4 people”) →
  the 4-person tent first, honestly marked out of stock; occasion words (“gift for a hiker under $50”) don't block a
  budget search; unmatched words with a budget say so before offering in-stock items; a product that exists above the
  budget still gets an honest “nothing within $100”.

## 6. Still unverified

Physical microphones and real voices (§2–3), native-speaker review of recognition and of the Tamil/Hindi texts,
other browsers (Safari's Web Speech fallback), mobile devices, and any model other than `base`.

## 7. Conversational acceptance (2026-11-10)

Fixes made after testing the four-turn scenario (Tamil → English → Tamil → Hindi):
* **Context across language switches:** follow-ups ("the best one…", "இதில்…", "इसकी कीमत") use the products named in
  the conversation; elliptical spoken questions ("मुजे कितनी है" — how much?) with no product words or budget of their own
  continue the topic too. Tamil references are matched by stem, so a transcript that drops the final mark still works.
* **Attribute questions** (colour, size, flavour, material, weight) are answered from the catalogue description, which
  is quoted, with a plain statement that no other options are listed (never invented).
* **Conversational cart removal** (new): "remove it from my cart" / "கார்ட்டிலிருந்து நீக்கு" / "कार्ट से हटा दो"
  offers a confirmation button; the cart changes only when it is tapped.
* **Relevance:** "hiking bag" / "Hi-King bag" / "bag" (not a sleeping bag) → packs; spoken Tamil spellings "காப்பி",
  "கொட்டை" → coffee / beans.
* **Unsupported scripts** (Telugu, Kannada, …) typed or transcribed → clarification instead of a reply in another language.
* **Speaking indicator:** "<assistant> is speaking" with a Stop button while a reply is read aloud.

Results:

| Test | Scout | Maple |
|---|---|---|
| Text, 4 turns, language and products kept (`test_multilingual_acceptance.py`) | 4/4 | 4/4 |
| Live dev API, same scenario | 4/4 | 4/4 |
| Spoken (whisper.cpp base, macOS voices), clean: language right first time / after one tap / context kept | 4/4 · 4/4 · 4/4 | 3/4 · 4/4 · 4/4 |
| Spoken, 15 dB noise: language / context | 4/4 · 0/4 | 4/4 · 0/4 (first Tamil turn too garbled to name a product) |
| Browser chat with substituted microphone (`e2e/voice.spec.cjs`): language right / interruption + speaking again | 4/4 · yes | 4/4 · yes |
| 12-turn conversation, no language drift | pass | pass |
| Wrong-language answers in all voice tests | 0 | 0 |

Run: `cd frontend && npm run test:e2e:voice`; backend voice tests with `AVC_TEST_WHISPER_MULTI_MODEL=models/whisper/ggml-base.bin`.

### Manual checklist still required (not verified)
Physical microphone (§2) in a quiet room, with background noise, at 1–2 m, with a headset; native Tamil and Hindi
speakers saying the four-turn scenario in their own words; review of every Tamil/Hindi reply text by native speakers.

# Phone integration

## Status

Only the **simulator** exists. It runs the real call logic over HTTP text turns and labels every
response `"simulated": true`. **No telephone network is involved, and no real call has been made.**

The simulator answers unauthenticated callers, so it is only reachable when `APP_ENV=development` (or with an explicit
`PHONE_SIMULATOR_ENABLED=true`); otherwise its endpoints return 404. Order-status verification (order number + shipping
postal code) is limited across calls, not only within one call (`backend/app/phone/session.py`). Failed verifications are
counted in a sliding 30-minute window at three levels, and verification is refused as soon as any one is reached:

| Limit | Failures per 30 minutes | Purpose |
|---|---|---|
| Per caller, per order | 3 | stops one caller retrying codes for one order |
| Per caller, any order | 5 | stops one caller sweeping many orders |
| Per order, any caller | 20 | stops many callers sharing one order's guesses, while one caller alone cannot lock a customer out |

While a limit is active, verification is refused **without looking the order up**, so the reply never reveals whether a
guess was right; the refusal tells the caller to sign in on the website or email support. A successful verification clears
only that caller's own per-order count. Within a single call, 3 failed attempts end the call. A caller can start at most
10 calls per 30 minutes (further attempts get `429` with `Retry-After: 1800`). The caller is identified by the client
address, taking `X-Forwarded-For` into account only from proxies listed in `TRUSTED_PROXIES`. Counters are in memory: they
reset when the API restarts and are not shared between instances, so a multi-instance deployment needs a shared store. If
the counter memory bound is reached while every tracked entry is an active lockout, verification is refused until entries
expire (it never forgets an active lockout).

## What a caller can do (simulator, `app/phone/session.py`)

Customers reach it from the storefront at **Contact us → Phone → Try the simulated customer-care call** (`/support/call`):
a browser page that speaks Scout's / Maple's answers aloud and takes the caller's voice (same speech engines as the chat),
keypad digits or typed text. It is labelled as a simulation everywhere.

| Caller says / does | What happens |
|---|---|
| (call starts) | Greeting in Tamil by default (or the language chosen on the page), naming the assistant and what it can do, and that English and Hindi work too |
| Any utterance | Language identified from the words (`assistant/language.py`); prompts follow it. "English" / "தமிழ்" / "हिंदी" alone switches explicitly |
| "Where is my order?" | Order number (spoken, spelled "S A one zero…", or keyed) → shipping PIN code (any script: ६२५५२१, ௬௨…, or digit words) → status, readable date ("Friday, 13 November"), carrier and tracking |
| Complaint, return, refund ("my headlamp arrived broken") | Verifies the order, then asks only for what is missing: item (pre-selected when the caller named it), reason, description (the caller's own words). Reads it back; saves only after "yes" / key 1. The reference the database returned is read out and spelled ("S A, C M P, 0 0 0 0 1"). Same rules as the website (`care_requests.py`): eligibility, return window, one open request per item, refunds simulated |
| Ineligible return / refund | Says why, offers a complaint (key 1) or a request for the team (key 2) |
| "Operator", "real person", "talk to someone" | Says honestly that **no one takes calls on this line** and offers to record a request for the team (`…-ESC-…`), after verifying an order; with no order, gives the support e-mail and hours. `transfer_to_agent` is never set |
| "Status of my complaint" | Requests on the **verified order only** |
| Silence | Asked again; never counted as a wrong PIN; three silent turns end the call politely |
| A different question mid-verification | Answered from the main menu (a sentence that merely contains a number is not a PIN guess) |
| "Cancel", "menu" | Back to the main menu; nothing recorded |
| "Thanks", "bye", "நன்றி", "धन्यवाद", "no" (to "anything else?") | Polite goodbye, call ends |

Privacy: a postal code is a weak secret, so a phone caller only ever hears about the one order they verified — never the
customer's other orders or requests. Requests recorded by phone appear for the customer under **My requests** and for staff
under **Staff → Customer care**, exactly like ones made on the website.

## Design

```
caller ─▶ telephony provider ─▶ provider adapter (webhook) ─▶ CallManager (session.py) ─▶ Assistant / repositories
                                    ▲ parse_inbound()                │
                                    └──────── render() ◀─────────────┘ OutboundTurn(say, expect_input, hang_up, transfer)
```

- `app/phone/base.py`: `PhoneProvider` with `parse_inbound(payload) -> InboundTurn` and
  `render(OutboundTurn) -> provider response`. Each provider needs one small adapter.
- `app/phone/session.py`: the provider-independent state machine:
  - greeting
  - general questions, answered by the shared assistant without any login
  - order status, which requires the order number and then the shipping PIN code (ZIP for old US orders); 3 failures end the call
  - customer-care requests (complaint, return, simulated refund, request for the team) on the verified order
  - requests for a person: recorded for staff, never a fake transfer
  - goodbye
- `app/phone/phone_text.py`: every phone prompt in Tamil, English and Hindi (not yet reviewed by a native speaker).
- The store is chosen by the number that was dialed: `PHONE_NUMBER_STORE_MAP` in `.env`, for example
  `+15550100001=store-a`.

## Requirements for a real provider

| Need | Notes |
|---|---|
| Provider account and phone number(s) | One number per store, e.g. Twilio or Vonage. This costs money, so get approval first. |
| Credentials | Account SID and auth token (or equivalent), stored in `.env` only, never committed |
| Public HTTPS webhook URL | The provider must reach `/api/phone/<provider>/...`. Locally that means a tunnel (ngrok or Cloudflare Tunnel); in production, a hosted HTTPS endpoint |
| Webhook signature verification | e.g. validate the `X-Twilio-Signature` header on every request |
| Speech | Use the provider's built-in speech-to-text and text-to-speech, e.g. Twilio `<Gather input="speech dtmf">` and `<Say>`. Note that this sends caller audio to the provider. Alternatively, stream audio to a local engine (see `voice.md`) |
| Human handoff | Only if a staffed queue exists: the call flow would need to set `transfer_to_agent` (today it never does, and requests for a person are recorded instead) |
| Compliance | Call-recording consent, data retention, and privacy notices for your region |

### Twilio example (not implemented)

1. `TwilioProvider.parse_inbound(form)` reads `CallSid` (call id), `SpeechResult` and `Digits`.
2. `render(turn)` returns TwiML: `<Response><Gather input="speech dtmf" action="/api/phone/twilio/turn"><Say>…</Say></Gather></Response>`,
   or `<Say>…</Say><Hangup/>` / `<Dial>` for the end and transfer cases.
3. Add the routes `POST /api/phone/twilio/voice` (incoming call, maps `To` to a store) and
   `POST /api/phone/twilio/turn`.

### Local SIP alternative

Asterisk or FreeSWITCH with a softphone can run entirely locally. Use AGI/ARI or a mod_audio_stream
bridge that turns speech into text and posts turns to the same `CallManager`.

## Speech for a future real phone channel

Local engines now exist behind the same adapters (see `docs/voice.md`): whisper.cpp for
speech-to-text and macOS `say` for text-to-speech. A SIP gateway or media-stream provider
could send caller audio to `WhisperCppSTT` and play `MacSayTTS` output, instead of relying on the provider's
own speech services. This is still **not connected to any telephone network**. Every phone
response remains `"simulated": true` until a real provider adapter is written, configured and authorised.

# Phone integration

## Status

Only the **simulator** exists. It runs the real call logic over HTTP text turns and labels every
response `"simulated": true`. **No telephone network is involved, and no real call has been made.**

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
  - order status, which requires the order number and then the shipping ZIP; 3 failures end the call
  - transfer to a person
  - goodbye
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
| Human handoff | A number or queue to route to when `transfer_to_agent` is true |
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

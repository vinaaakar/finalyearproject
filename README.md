# AI Voice Commerce — Inclusive Customer Service for Two Stores

Two independent e-commerce storefronts served by **one central AI customer-service assistant**.
Customers can browse, add to a cart, check out, pay (sandbox), manage an account, and ask the assistant —
by typing or by speaking — about products, prices, stock, shipping, returns, their cart and order status.
Each store has its own database; nothing is shared between them. The assistant speaks **Tamil (default),
English and Hindi**: it identifies the language of every message from the customer's own words and replies, in
text and speech, in that language (see docs/voice.md).

| | Store A | Store B |
|---|---|---|
| Brand | **Summit Trail Co.** (outdoor gear) | **Bloom & Brew** (coffee, tea, kitchen) |
| Assistant | Scout | Maple |
| Storefront | http://127.0.0.1:5180 | http://127.0.0.1:5181 |
| Database | `store_a` (role `store_a_app`) | `store_b` (role `store_b_app`) |
| Order numbers | `SA-xxxxx` | `BB-xxxxx` (new orders start at 50001) |
| Shipping | $6.95, free over $75, expedited $14.95; contiguous US only | $4.99, free over $50 |

All data is **synthetic** (fictional people, `example.com` emails). **Payments are sandbox-only**:
no real money moves and no card details are collected anywhere.

---

## Quick start

Prerequisites (already on this machine): Docker Desktop, Node.js ≥ 18, Python ≥ 3.11, Ollama with `llama3.2:3b`.

```bash
cd ~/Projects/ai-voice-commerce
scripts/setup.sh     # one time: .env with random secrets, Postgres container, venv, migrations, seed, npm install
scripts/start.sh     # API :8000, Store A :5180, Store B :5181 (logs in .run/)
scripts/test.sh      # backend tests + storefront production builds
scripts/stop.sh      # stop app processes (add --db to also stop the Postgres container; data is kept)
```

After pulling new code, apply migrations without touching existing data:
`cd backend && .venv/bin/python -m app.migrate && .venv/bin/python -m app.seed` (the seed step only backfills new settings when data exists).

If Ollama is not running, the assistant automatically uses deterministic rule-based replies.

### Demo accounts (synthetic)

| Store | Email | Password | Role |
|---|---|---|---|
| A | `alex.rivera@example.com` | `TrailDemo!2026` | customer (orders SA-10001, SA-10002) |
| A | `jordan.lee@example.com` | `TrailDemo!2026` | customer |
| A | `agent@summittrail.example.com` | `AgentDemo!2026` | staff agent |
| B | `maria.gomez@example.com` | `BrewDemo!2026` | customer (orders BB-20001, BB-20004) |
| B | `alex.rivera@example.com` | `BrewDemo!2026` | customer — a *separate* account from Store A's Alex |
| B | `agent@bloomandbrew.example.com` | `AgentDemo!2026` | staff agent |

You can also create accounts at `/register` (per store). Password reset emails are not sent; in
development they are written to `.run/outbox/` (git-ignored, owner-only files).

Phone-verification ZIP codes: SA-10001 → `80302`, BB-20001 → `60614` (see `backend/app/seed.py`).

---

## Architecture

```
 Store A (React/Vite :5180)      Store B (React/Vite :5181)
        │  /api proxy                     │  /api proxy
        └──────────────┬──────────────────┘
                       ▼
          Central FastAPI backend (:8000)
   ┌──────────────────────────────────────────────────────┐
   │ store id validated (enum) → token must match store    │
   │ AND a live server-side session → role → rate limit     │
   │                                                        │
   │ Commerce (commerce.py): cart, checkout transaction,    │
   │   order/payment state machine (order_state.py)         │
   │ Payments (payments/): provider interface + SANDBOX     │
   │ Accounts: register, sessions, sign-out, password reset │
   │ Assistant: intent rules → controlled repo calls        │
   │   → private + catalogue answers deterministic; policy   │
   │   answers phrased by Ollama → strict grounding → rules │
   │ Speech: browser STT/TTS, or local whisper.cpp / `say`  │
   │ Phone: provider interface + call state machine (sim)   │
   └──────────┬───────────────────────┬────────────────────┘
              ▼                       ▼
     Postgres db store_a       Postgres db store_b      (container avc_postgres, 127.0.0.1:5433)
     role store_a_app only     role store_b_app only
```

Project layout:

```
backend/            FastAPI app (app/), SQL migrations, tests, venv (.venv, git-ignored)
  app/commerce.py   cart, checkout, payment flows (all SQL for these lives here)
  app/order_state.py order + payment state machines
  app/payments/     provider interface (base.py) + sandbox provider
  app/assistant/    intent rules, Ollama client, assistant service
  app/phone/        provider interface, call state machine, simulator
  app/speech/       speech adapters (whisper.cpp STT, macOS say TTS)
  app/notify.py     email adapters (dev outbox only)
frontend/           npm workspace (one shared node_modules)
  packages/shared/  shared React UI: pages, chat widget, voice adapters, API client, styles
  apps/store-a/     Summit Trail Co. branding + config
  apps/store-b/     Bloom & Brew branding + config
db/init/            creates per-store databases and roles on first container start
scripts/            setup / start / stop / test / backup_to_drive
docs/               voice and phone integration notes
```

## Security model

- **Physical isolation**: each store has its own database *and* its own Postgres role; `CONNECT`
  is revoked from `PUBLIC`, so Store A's role cannot even open Store B's database (tested). Carts,
  orders, payments, sessions and reset tokens live in the store's own database, so a Store A cart
  token, order or payment reference cannot even be addressed from Store B.
- **Sessions**: login/registration create a server-side session row (only a SHA-256 of its id is
  stored). Access tokens are HMAC-signed, carry the store id and the session id, and are accepted only
  while that session is live. Sign-out revokes it; a password reset revokes all of the customer's sessions.
  A Store A token on any Store B endpoint gets `403`; a tampered or session-less token gets `401`.
- **Accounts**: scrypt password hashes; minimum 10 characters plus a common-password check; emails unique
  per store (case-insensitive); registration can never create a staff account (unknown fields are rejected).
  Password-reset requests answer identically whether or not the email exists. Reset tokens are random,
  stored hashed, expire after 30 minutes, are single-use and store-scoped, and are sent in the URL *fragment*
  so they never reach server logs or Referer headers.
- **Cart & checkout**: the cart stores only product ids and quantities. Every price, subtotal, shipping
  charge and total is computed on the server from the database. Checkout locks the product rows,
  re-checks stock and prices, and creates the order, its items and the stock decrement in **one transaction**.
  It requires an `Idempotency-Key`: repeated or concurrent submissions return the original order (tested with
  4 parallel submissions). If the total changed since the customer reviewed it, checkout stops with `409`.
  Addresses are validated on the server (US state, ZIP format; Store A refuses AK/HI).
- **Payments**: provider interface plus a **sandbox** provider. The order moves to "processing" only
  after the server asks the provider for the status and the amount and currency match the order;
  the verify endpoint takes no status from the client. No card fields exist anywhere (unknown fields are
  rejected). Selecting any non-sandbox provider is refused unless `PAYMENT_LIVE_AUTHORIZED=true`,
  and no live provider is implemented.
- **Order privacy**: order details only for the signed-in owner, or a staff agent of the same store.
  Unknown orders and other people's orders return the same `404`.
- **The LLM never touches the database.** The backend picks intents with rules and fetches data through
  fixed, parameterised functions. Answers about **orders and carts are always deterministic**: the model
  is not called. Other model replies are checked against the verified context (dollar amounts, order
  numbers, the other store's name or assistant) and replaced with the rule-based answer if they fail.
  Identity comes only from the session or the shopper's own cart token, never from message text
  (claimed roles, fake JSON and forged chat history are tested).
- **Input validation** (Pydantic, unknown fields forbidden on commerce/account bodies); errors never echo values.
- **Rate limiting** per client IP: login 10/min, account actions (register/reset) 10/min, chat and speech
  30/min, everything else 120/min.
- **Logs and errors** contain no tokens, passwords, credentials, audio or email bodies. `Settings`
  hides the secret key and database URLs from `repr`, so they don't appear in tracebacks.
- **Phone callers** must give both the order number and the shipping ZIP; 3 failures end the call.

## Customer care

Scout and Maple handle deliveries, cancellations, payments, refunds, returns, damaged or wrong items, accounts,
checkout help, product comparison and alternatives, promotions, invoices, privacy, accessibility and requests for a
person, in Tamil, English and Hindi, typed or spoken. Customer-specific answers come only from the signed-in
customer's own records. The assistant can propose **actions** (links, *Add to cart*, *Cancel order* for unpaid
orders with a second confirmation); the existing APIs perform and validate them, and the chat confirms only after
they succeed. Capabilities the system doesn't have (refunds, returns, edits, tickets, live agents…) are explained
honestly with the store's support contact. Details: **docs/customer-care.md**.

## Voice and languages

See **docs/voice.md** for details and measured results. In short:
- **Tamil is the default**: the chat widget opens in Tamil (welcome, chips, prompts, selector). Only Tamil, English
  and Hindi are offered.
- **Per-utterance language identification**: local whisper.cpp language detection (multilingual model), combined
  with text evidence (script, romanized Tamil/Hindi words). The acoustic result is accepted only in a receipt signed by
  the server. Uncertain or unsupported → a clarification with தமிழ் / English / हिन्दी buttons, never a guess.
  Language-neutral messages use the conversation language and are labelled as not detected.
- **Replies in the same language**: Tamil and Hindi come from reviewed templates and translated store policies, with
  facts inserted verbatim. English policy/greeting/contact answers may be phrased by the LLM, with language and strict
  grounding enforced on the server; product, price and stock answers always come from catalogue rows (docs/customer-care.md).
- **Speech in the same language**: local macOS voices Vani (ta-IN), Lekha (hi-IN), Rishi (en-IN) in the browser. Remote
  voices are never used. Fallback: server `say`, then text only with a notice.
- Audio stays on this Mac when local STT is enabled. Without it, the browser's Web Speech API listens in one fixed
  locale (it cannot detect language) and Chrome sends that audio to Google. The widget says which mode is active.
- Local speech is **off by default**; see docs/voice.md for the `.env` lines. A multilingual model is required for Tamil/Hindi.

## Phone

A provider-independent interface plus a call state machine. Only a **text-based simulator** exists; every
response contains `"simulated": true` and a `SIMULATION ONLY` notice. **No real phone calls are possible.** The simulator is
enabled only in development (`PHONE_SIMULATOR_ENABLED` overrides) and limits order-verification guessing across calls.
See `docs/phone-integration.md`.

## API overview

Interactive docs: http://127.0.0.1:8000/docs. `{store}` is `store-a` or `store-b`; anything else gets `422`.

| Method | Path | Auth |
|---|---|---|
| GET | `/api/health` | — |
| GET | `/api/stores/{store}` · `/categories` · `/products?q=&category=` · `/products/{slug}` | — |
| POST | `/api/stores/{store}/auth/login` · `/auth/register` | — |
| POST | `/api/stores/{store}/auth/logout` | signed in |
| POST | `/api/stores/{store}/auth/password-reset/request` · `/auth/password-reset/confirm` | — |
| GET | `/api/stores/{store}/me` · `/orders` · `/orders/{order_number}` | customer or agent |
| GET | `/api/stores/{store}/admin/orders` | agent |
| GET | `/api/stores/{store}/cart` | guest (`X-Cart-Token`) or customer |
| POST/PUT/DELETE | `/api/stores/{store}/cart/items` · `/cart/items/{slug}` | guest or customer |
| POST | `/api/stores/{store}/cart/merge` | customer (+ guest `X-Cart-Token`) |
| POST | `/api/stores/{store}/checkout/quote` | customer |
| POST | `/api/stores/{store}/checkout` (header `Idempotency-Key`) | customer |
| POST | `/api/stores/{store}/orders/{n}/cancel` · `/orders/{n}/payments` · `/orders/{n}/payments/verify` | customer (owner) |
| GET | `/api/stores/{store}/orders/{n}/payment` | customer (owner) |
| POST | `/api/stores/{store}/payments/sandbox/{ref}/complete` | customer (owner), sandbox only |
| POST | `/api/stores/{store}/chat` (`conversation_language`, `speech_receipt`, `language_override`) | optional (needed for orders; cart via session or `X-Cart-Token`) |
| GET | `/api/speech/capabilities` | — |
| POST | `/api/stores/{store}/speech/transcribe?language=auto` (WAV body) · `/api/speech/synthesize` (`{text, language}`) | — (rate-limited) |
| POST | `/api/phone/simulator/{store}/calls` · `/api/phone/simulator/calls/{id}/turns` | — (simulation) |

## Configuration

`.env` (created by `scripts/setup.sh`, permissions `600`, git-ignored). See `.env.example` for every
variable, including `PAYMENT_PROVIDER`, `EMAIL_DELIVERY`, `STORE_*_PUBLIC_URL`, `SPEECH_STT`,
`WHISPER_MODEL_PATH`, `SPEECH_TTS`. `python -m app.config` (from `backend/`) validates it; `start.sh` runs it.

Database changes: add `backend/migrations/000N_description.sql`, then `python -m app.migrate`.
Reseed demo data (destructive): `python -m app.seed --reset`.

## Testing

`scripts/test.sh` runs the service-script safety tests, then the backend tests against separate `store_a_test` /
`store_b_test` databases (never the dev data), then builds both storefronts. Latest verified backend run (2026-11-09):
**446 tests collected — 439 passed, 7 skipped** (the skipped ones are the real speech-engine tests, which need the model
paths described below). Coverage added since the first version:
cart pricing and stock rules, guest-cart merge, checkout transaction, idempotency (including concurrent
submissions), price/stock re-checks, address validation, sandbox payments (approve, decline + retry,
amount mismatch, client claims ignored, cancelled orders), order state machine, registration, sign-out
revocation, password reset (single-use, expiry, store-scoped, no account enumeration), assistant grounding,
private answers never sent to the model, claimed identities and forged history, cross-store tokens for
chat/cart/payments, and speech endpoints. Key protections were mutation-checked: disabling them makes tests fail.

Multilingual tests (`tests/test_multilingual.py`, `tests/test_speech_languages.py`) cover Tamil default, per-utterance
identification, ta→en→hi→ta switching, the selector not acting as evidence, neutral/uncertain fallbacks, receipt
forgery, security in all three languages, identical facts across languages, and LLM language enforcement.

The real-engine speech tests run when `AVC_TEST_WHISPER_MODEL=/path/to/ggml-base.en.bin` and
`AVC_TEST_WHISPER_MULTI_MODEL=/path/to/ggml-base.bin` are set; otherwise they are skipped.

Browser end-to-end checks were run in headless Chrome (driven over the DevTools protocol) against an
isolated stack on the test databases: guest cart → sign-in merge → checkout → double-clicked "Place order"
(one order created) → declined then approved sandbox payment → order processing → assistant reports it →
sign-out revokes the token; registration and password reset via the outbox link; HI address refused; 390 px layouts;
and the local voice loop using Chrome's fake microphone device.

## What works vs. what doesn't

**Working and verified**
- Both storefronts: catalog, search, product detail, **cart, checkout, sandbox payment, registration,
  sign-in/out, password reset**; responsive at 390 px, 768 px and desktop (rendered in headless Chrome).
- Central assistant with live `llama3.2:3b` and rule-based fallback; budget-aware recommendations;
  cart and order answers; grounding check (live: an injection asking about the other store fell back to rules).
- Cross-store isolation for accounts, sessions, carts, orders, payments, assistant and phone.
- Local voice: whisper.cpp STT and macOS `say` TTS, end-to-end in Chrome with a fake mic device.
- Phone call flow in simulation.

- Tamil/English/Hindi chat with automatic per-utterance language identification and matching speech
  (engine-level tests with macOS voices; browser tests with injected audio fixtures and Chrome's fake microphone).

**Implemented but not verified by a person**
- A **physical microphone** with a real voice (any language, including Indian-accented speech), and the
  browser-vendor Web Speech recognizer (in headless Chrome it returned no result). Please press 🎤 in Chrome or Safari.
- Short Tamil utterances can be heard as Telugu by `ggml-base`, which leads to a clarification. A larger model would help (not downloaded).

**Not implemented**
- A real payment provider (needs an account, keys and your explicit authorisation).
- Sending real email (password reset uses the dev outbox).
- Expiry of unpaid orders (pending orders keep their reserved stock until paid or cancelled).
- Refund flow for a payment that succeeds after an order was cancelled (logged as a warning only).
- Staff tools to move orders to shipped/delivered (the state machine supports it; no endpoint yet).
- A real telephony provider; HTTPS and production hosting; shared rate-limit storage for multiple instances.
- Tokens are kept in `sessionStorage` (bearer tokens, revocable server-side). An httpOnly-cookie session with
  CSRF protection would be stronger against XSS for production.

## Storage notes

The app adds about **270 MB** locally (venv ~67 MB, node_modules ~44 MB, plus the Postgres volume).
No models were downloaded: local STT reuses the existing `whisper-cli` and the `ggml-base.en.bin` model in
`~/.baymax/models` (read-only). **The disk had only about 2 GB free** during this work, so free some space before
downloading anything larger. `scripts/backup_to_drive.sh` (run manually) writes a source + database-dump
archive, **excluding `.env`**, to `My Drive/AI-Voice-Commerce/project-backups`.

## Troubleshooting

- `python3` crashes on this Mac (the python.org 3.13 build first on PATH). Scripts use `/opt/homebrew/bin/python3`;
  override with `PYTHON=/path/to/python3`.
- Port 5432 is used by another project's Postgres; this project uses **5433**. Port 5173 is busy, so the
  storefronts use **5180/5181**.
- Replies tagged "quick answer" came from the deterministic path: order/cart answers always do,
  and other answers do when Ollama is off or a model reply failed the grounding check.
- After this update, sign in again: tokens issued before sessions existed are rejected.

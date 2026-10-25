# AI Voice Commerce — Inclusive Customer Service for Two Stores

Two independent e-commerce storefronts served by **one central AI customer-service assistant**.
Customers can browse products, sign in, view orders, and ask the assistant — by typing or by
speaking — about products, prices, stock, shipping, returns and order status. Each store has its
own database; the assistant never mixes their data.

| | Store A | Store B |
|---|---|---|
| Brand | **Summit Trail Co.** (outdoor gear) | **Bloom & Brew** (coffee, tea, kitchen) |
| Assistant | Scout | Maple |
| Storefront | http://127.0.0.1:5180 | http://127.0.0.1:5181 |
| Database | `store_a` (role `store_a_app`) | `store_b` (role `store_b_app`) |
| Order numbers | `SA-xxxxx` | `BB-xxxxx` |

All data is **synthetic** (fictional people, `example.com` emails).

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

If Ollama is not running, the assistant automatically uses deterministic rule-based replies.
Start Ollama with `ollama serve` (or open the Ollama app); no restart of the API is needed.

### Demo accounts (synthetic)

| Store | Email | Password | Role |
|---|---|---|---|
| A | `alex.rivera@example.com` | `TrailDemo!2026` | customer (orders SA-10001, SA-10002) |
| A | `jordan.lee@example.com` | `TrailDemo!2026` | customer |
| A | `agent@summittrail.example.com` | `AgentDemo!2026` | staff agent |
| B | `maria.gomez@example.com` | `BrewDemo!2026` | customer (orders BB-20001, BB-20004) |
| B | `alex.rivera@example.com` | `BrewDemo!2026` | customer — a *separate* account from Store A's Alex |
| B | `agent@bloomandbrew.example.com` | `AgentDemo!2026` | staff agent |

Phone-verification ZIP codes: SA-10001 → `80302`, BB-20001 → `60614` (see `backend/app/seed.py`).

---

## Architecture

```
 Store A (React/Vite :5180)      Store B (React/Vite :5181)
        │  /api proxy                     │  /api proxy
        └──────────────┬──────────────────┘
                       ▼
          Central FastAPI backend (:8000)
   ┌───────────────────────────────────────────────┐
   │ store id validated (enum) → auth token must    │
   │ match store → role check → rate limit           │
   │                                                 │
   │ Assistant: intent rules → controlled repo calls │
   │   → context (this store + this customer only)   │
   │   → Ollama llama3.2:3b phrases reply            │
   │   → fallback: deterministic reply               │
   │ Phone: provider interface + call state machine  │
   │ Speech: adapter slots (browser STT/TTS today)   │
   └──────────┬───────────────────────┬──────────────┘
              ▼                       ▼
     Postgres db store_a       Postgres db store_b      (container avc_postgres, 127.0.0.1:5433)
     role store_a_app only     role store_b_app only
```

Project layout:

```
backend/            FastAPI app (app/), SQL migrations, tests, venv (.venv, git-ignored)
  app/assistant/    intent rules, Ollama client, assistant service
  app/phone/        provider interface, call state machine, simulator
  app/speech/       server-side speech adapter slots
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
  is revoked from `PUBLIC`, so Store A's role cannot even open Store B's database (tested).
- **Store-bound sessions**: login tokens are HMAC-signed and contain the store id. A Store A token
  sent to any Store B endpoint gets `403`. Tampering with the token gets `401`.
- **Order privacy**: order details are returned only to the signed-in owner, or to a staff agent of
  the same store. Unknown and other people's orders both return the same `404`. Login failure messages
  do not reveal whether an email exists (and timing is equalised).
- **The LLM never touches the database.** The backend decides intents with deterministic rules and
  fetches data through fixed, parameterised functions in `app/repositories.py`. The model only receives
  the current store's data and the current customer's own orders, so prompt injection cannot extract
  other data. Guests asking about orders get a sign-in prompt; no order data is sent to the model.
- **Input validation** (Pydantic) with length limits; validation errors never echo submitted values.
- **Rate limiting** per client IP: login 10/min, chat 30/min, everything else 120/min (configurable).
- **Errors** are uniform JSON (`{"error": {"code", "message"}}`) with no stack traces.
- **Logs** contain method, path, status, duration and request id only; a redaction filter strips
  bearer tokens, passwords and database credentials.
- **Phone callers** must give both the order number and the shipping ZIP; 3 failures end the call.

## Voice (Milestone 3)

- 🎤 button in the chat widget uses the browser's **Web Speech API** (Chrome, Edge, Safari).
  Interim text appears live; the final transcript is sent as a chat message and the reply is spoken.
- Replies are spoken with **`speechSynthesis`**, which runs locally using the OS voices.
  "Read replies aloud" makes typed questions spoken too.
- Microphone denial, missing microphones, unsupported browsers and non-secure pages show a clear
  message, and typing always keeps working.
- **Privacy note:** Chrome/Edge send microphone audio to the browser vendor's cloud speech service.
  This is disclosed in the widget. A fully local option (whisper.cpp / faster-whisper behind the
  `app/speech` adapter) is documented in `docs/voice.md` but **not installed**, to avoid a large download.

## Phone (Milestone 4)

A provider-independent interface (`app/phone/base.py`) plus a shared call state machine
(`app/phone/session.py`). Only a **text-based simulator** exists today; every simulator response
contains `"simulated": true` and a `SIMULATION ONLY` notice. **No real phone calls are possible yet.**
See `docs/phone-integration.md` for what a real provider (Twilio, a SIP gateway, …) needs.

```bash
curl -s -X POST localhost:8000/api/phone/simulator/store-a/calls
curl -s -X POST localhost:8000/api/phone/simulator/calls/<call_id>/turns -H 'Content-Type: application/json' -d '{"speech":"where is my order SA-10001"}'
curl -s -X POST localhost:8000/api/phone/simulator/calls/<call_id>/turns -H 'Content-Type: application/json' -d '{"digits":"80302"}'
```

## API overview

Interactive docs: http://127.0.0.1:8000/docs

| Method | Path | Auth |
|---|---|---|
| GET | `/api/health` | — |
| GET | `/api/stores/{store}` · `/categories` · `/products?q=&category=` · `/products/{slug}` | — |
| POST | `/api/stores/{store}/auth/login` | — |
| GET | `/api/stores/{store}/me` · `/orders` · `/orders/{order_number}` | customer or agent |
| GET | `/api/stores/{store}/admin/orders` | agent |
| POST | `/api/stores/{store}/chat` | optional (needed for order status) |
| GET | `/api/speech/capabilities` | — |
| POST | `/api/phone/simulator/{store}/calls` · `/api/phone/simulator/calls/{id}/turns` | — (simulation) |

`{store}` is `store-a` or `store-b`; anything else is rejected with `422`.

## Configuration

`.env` (created by `scripts/setup.sh`, permissions `600`, git-ignored). See `.env.example` for every
variable. `python -m app.config` (run from `backend/`) validates it; `start.sh` does this automatically.
Invalid values are reported by variable name only — values are never printed.

Database changes: add `backend/migrations/000N_description.sql`, then `python -m app.migrate`.
Reseed demo data: `python -m app.seed --reset`.

## Testing

`scripts/test.sh` runs **59 backend tests** against separate `store_a_test` / `store_b_test` databases
(never the dev data), then builds both storefronts. Coverage includes:
cross-store isolation at API, assistant, phone and database-role level; auth and roles; the assistant
with a fake LLM (context contains only the current store); LLM-failure fallback; prompt-injection
attempts; validation; rate limits; config validation; token tampering/expiry; log redaction; phone flows.

## What works vs. what doesn't

**Working and verified**
- Both storefronts: catalog, search, category filter, product detail, sign-in, order list, staff order list;
  responsive at desktop and 390 px phone width (rendered in headless Chrome).
- Central assistant with live `llama3.2:3b` (≈1–2 s per reply on this Mac) and automatic rule-based fallback.
- Secure order-status lookup in chat; cross-store isolation; rate limiting; error handling.
- Phone call flow in simulation.

**Implemented but not verified by an automated or manual test here**
- Microphone input and spoken replies in a real browser. The code builds, but nobody has clicked the
  🎤 button with a real microphone yet. Please try it in Chrome or Safari.
- Chat widget interactions in the browser (the API it calls is fully tested; the UI was not click-tested).

**Not implemented**
- Cart, checkout, payments, account registration and password reset.
- A local server-side speech engine (only the adapter slot exists).
- A real telephony provider (needs an account and credentials, or a local SIP setup).
- Shared rate-limit storage for multi-instance deployments (the current limiter is in-memory).
- HTTPS and production hosting configuration.

## Storage notes

The app adds about **270 MB** locally: venv ~67 MB, node_modules ~44 MB, plus the Postgres volume.
It reuses the existing `postgres:15-alpine` image and the existing `llama3.2:3b` model; nothing large
was downloaded. `scripts/backup_to_drive.sh` (run it manually) writes a source + database-dump archive,
**excluding `.env`**, to `My Drive/AI-Voice-Commerce/project-backups` with a SHA-256 checksum.
Active code, the venv and the database stay on the local disk.

## Troubleshooting

- `python3` crashes on this Mac (the python.org 3.13 build that's first on PATH). The scripts
  automatically use `/opt/homebrew/bin/python3`; override with `PYTHON=/path/to/python3`.
- Port 5432 is used by another project's Postgres; this project uses **5433**. Port 5173 is also busy,
  so the storefronts use **5180/5181**.
- Assistant replies tagged "quick answer" mean the rule-based fallback was used (Ollama is off or slow).

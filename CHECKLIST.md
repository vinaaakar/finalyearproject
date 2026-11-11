# Implementation Checklist

Status legend: [x] done & verified · [~] implemented, partially verified · [ ] not done

## Milestone 1 — Foundation
- [x] Project structure (backend / frontend workspaces / db / scripts / docs)
- [x] Postgres container `avc_postgres` (127.0.0.1:5433) with separate `store_a` / `store_b` databases and per-store DB roles
- [x] SQL migrations + migration runner, synthetic seed data (0002 applied to dev data without loss)
- [x] FastAPI backend: store registry, product + order APIs scoped by store
- [x] Central assistant: intent rules → verified context → Ollama `llama3.2:3b` with deterministic fallback
- [x] Store A (Summit Trail Co., :5180) and Store B (Bloom & Brew, :5181), shared component package
- [x] Product list, search, category filter, product detail; responsive (390 / 768 / 1280 px in headless Chrome)
- [x] Order-status lookup with seeded demo data
- [x] Chat widget UI click-tested in headless Chrome (chips, typed messages, sign-in prompt, order cards)

## Milestone 2 — Security
- [x] Customer login (scrypt), HMAC-signed store-bound tokens bound to server-side sessions, roles
- [x] Order data only for the owning customer or a same-store agent; identical 404s
- [x] Input validation, rate limiting, uniform JSON errors
- [x] LLM never touches the DB; only controlled repository functions
- [x] Cross-store tests (API, assistant, phone, cart, payments, DB-role level); mutation-checked
- [x] Secrets hidden from `Settings` repr (found when a test traceback printed the secret key)
- [x] First git commit (e14e9d5) after a secret scan; `.gitignore` hardened

## Milestone 3 — E-commerce
- [x] Cart: add / remove / change quantity; server-side totals and shipping; stock and per-line limits; guest cart token + merge on sign-in; per-store
- [x] Checkout: shipping form → review → place order; server validation; stock + price re-check; single transaction; Idempotency-Key (incl. concurrent duplicates); no card data
- [x] Accounts: registration, sign-in, server-revocable sign-out, password reset (hashed, single-use, 30 min, store-scoped, no enumeration), dev email outbox
- [x] Payments: provider interface + sandbox provider; server-side verification; amount check; decline + retry; cancel unpaid order (restock); live providers refused without explicit authorisation
- [x] Order / payment state machine with compare-and-set transitions
- [x] Browser E2E of the whole purchase flow (29 checks) on an isolated test stack
- [ ] Real payment provider (needs account + your authorisation)
- [ ] Real email delivery
- [ ] Expire unpaid orders; refund path for late payments; staff order-status tools

## Milestone 4 — Assistant
- [x] Recommendations only from the selected store's catalog; budget filter ("under ₹5,000"; a dollar budget is not converted); in-stock first
- [x] Shipping answers include the store's real rates (policy text tested to match checkout rates)
- [x] Cart questions answered from the owner's cart only (session or own cart token)
- [x] Order and cart answers are deterministic (model never called)
- [x] Grounding check on model replies (prices, order numbers, other store) → fallback
- [x] Prompt-injection / claimed-identity / forged-history / wrong-store tests
- [x] Rule-based fallback when Ollama is down (tested with an unreachable endpoint)

## Milestone 5 — Voice
- [x] Modular adapters: browser STT/TTS, local whisper.cpp STT, macOS `say` TTS (`/api/speech/capabilities`)
- [x] Local STT verified: real `say` → whisper.cpp round trip in tests; browser flow with Chrome's fake mic device
- [x] Browser `speechSynthesis` verified to finish speaking a reply (headless Chrome)
- [x] Mic-denied message verified in Chrome; unsupported/insecure messages implemented
- [~] Physical microphone with a real voice — needs a person to press 🎤 once
- [~] Browser-vendor Web Speech recognizer — mocked only; headless Chrome returned no result
- [ ] Enable local speech in `.env` (4 lines in docs/voice.md; nothing to download)

## Milestone 5b — Tamil / English / Hindi
- [x] Only ta / en / hi offered; Tamil default for new conversations (welcome, chips, prompts, selector) — browser-tested
- [x] Per-utterance language identification: whisper.cpp detection (multilingual model) + text evidence; signed speech receipts
- [x] Uncertain / unsupported → clarification in the conversation language; explicit choice re-transcribes the same audio
- [x] Language-neutral messages use the conversation language and are labelled "not detected"
- [x] Replies in the identified language (templates + translated policies); facts identical across languages (tested)
- [x] Backend enforces reply language: LLM only for English, drift into other scripts rejected (bug found and fixed)
- [x] Speech in the matching language with local voices (Vani / Lekha / Rishi); remote voices excluded; server-`say` and text-only fallbacks
- [x] Store-independent conversation language; security unchanged in all languages (tested)
- [x] Engine-level spoken switching test (ta→en→hi→ta, 4/5 identified, 1 clarified); browser fixture + fake-mic tests
- [x] Enabled in the dev `.env`; continuous spoken demo on the dev app: ta → en → hi → ta, 4/4 (substitute microphone)
- [x] Chrome fake-microphone device per utterance: 3/4 acoustic top-1 correct, 4/4 replies in the spoken language
- [~] Physical microphone / real voices — needs a person
- [ ] Dedicated multilingual model copy (testing used a read-only copy in another app's container); larger model for Tamil vs Telugu

## Milestone 5c — Customer care (Scout & Maple)
- [x] Care intents in ta/en/hi (delivery problems, cancel, modify, payment issues, refunds, returns/exchanges, damaged/wrong/missing, account, checkout, promotions, invoices, privacy, languages, accessibility, tech issues, bulk, reorder, care tips, frustration, human requests)
- [x] Verified answers from the customer's own orders and payment records; cross-store and cross-customer isolation kept
- [x] Proposed actions: links, add to cart, cancel unpaid order (two-step confirm); confirmed only after the API succeeds
- [x] Honest handling of unsupported capabilities, escalation to the store's support contact, repeated-failure escalation
- [x] Secrets in chat detected, never used or sent to the model; care answers never use the model
- [x] 76 tests (`tests/test_customer_care.py`); browser checks of the action buttons on an isolated stack (25/25)
- [ ] Native-speaker review of the Tamil and Hindi care templates
- [ ] Resolve the "prepaid return label" policy text (no such feature in the app)
- [ ] Physical-microphone test of care questions

## Milestone 6 — Phone
- [x] Provider-independent interface + call state machine
- [x] Simulator adapter, always labelled `simulated: true`; order number + postal-code verification (six-digit PIN for India orders, ZIP for legacy US demo orders), 3-strike lockout; works for new orders
- [x] Integration requirements doc (docs/phone-integration.md)
- [ ] Real telephony provider — needs credentials / SIP setup

## Milestone 7 — Production readiness
- [x] setup / start / stop / test scripts; manual `backup_to_drive.sh` (excludes .env; not yet run)
- [x] Env-variable validation (`python -m app.config`, run by start.sh)
- [x] Log redaction of tokens, passwords, DB credentials
- [ ] HTTPS, hosting, shared rate-limit store, httpOnly-cookie sessions + CSRF

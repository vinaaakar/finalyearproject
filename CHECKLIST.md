# Implementation Checklist

Status legend: [x] done & verified · [~] implemented, partially verified · [ ] not done

## Milestone 1 — Foundation
- [x] Project structure (backend / frontend workspaces / db / scripts / docs)
- [x] Postgres container `avc_postgres` (127.0.0.1:5433) with separate `store_a` / `store_b` databases and per-store DB roles
- [x] SQL migrations + migration runner, synthetic seed data
- [x] FastAPI backend: store registry, product + order APIs scoped by store
- [x] Central assistant: intent rules → verified context → Ollama `llama3.2:3b` (live, ~1–2 s) with deterministic fallback
- [x] Store A (Summit Trail Co., :5180) and Store B (Bloom & Brew, :5181), shared component package
- [x] Product list, search, category filter, product detail; responsive (rendered at 1280 px and 390 px)
- [x] Order-status lookup with seeded demo data
- [~] Chat widget UI — builds and renders; its API is fully tested; not click-tested in a browser

## Milestone 2 — Security
- [x] Customer login (scrypt hashes), HMAC-signed store-bound tokens, roles (customer / agent)
- [x] Order data only for the owning customer or a same-store agent; identical 404s
- [x] Input validation, rate limiting (login/chat/default), uniform JSON errors
- [x] LLM never touches the DB; only controlled repository functions
- [x] Tests proving Store A cannot access Store B (API, assistant, phone, DB-role level); mutation-checked

## Milestone 3 — Voice
- [x] Modular adapters: browser STT, server STT/TTS slots (`/api/speech/capabilities`), browser TTS
- [~] Mic button, live transcript, spoken replies — implemented and built, not yet tried with a real microphone
- [~] Mic denial / unsupported browser / insecure origin messages — implemented, not browser-tested
- [ ] Local server-side STT engine (documented in docs/voice.md; needs a model download)

## Milestone 4 — Phone
- [x] Provider-independent interface + call state machine
- [x] Simulator adapter, always labelled `simulated: true`; order number + ZIP verification, 3-strike lockout
- [x] Integration requirements doc (docs/phone-integration.md)
- [ ] Real telephony provider — needs credentials / SIP setup

## Milestone 5 — Production readiness
- [x] setup / start / stop / test scripts; manual `backup_to_drive.sh` (excludes .env; not yet run)
- [x] Env-variable validation (`python -m app.config`, run by start.sh)
- [x] Log redaction of tokens, passwords, DB credentials (tested; live logs scanned clean)
- [x] README with what works / what doesn't
- [ ] HTTPS, hosting, shared rate-limit store, cart/checkout, registration, password reset

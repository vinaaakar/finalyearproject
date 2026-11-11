# Production deployment (Phase J)

**Nothing has been deployed.** This is a deployable configuration plus the procedures to run it. A public deployment
needs your explicit authorisation and the credentials and decisions listed in §2.

## 1. Architecture (single host to start)

```
Internet ──443/80──► web (Caddy)  ── automatic HTTPS for STORE_A_DOMAIN and STORE_B_DOMAIN, HTTP→HTTPS, storefront headers/CSP
                       │  /            static build of each storefront (separate site per store)
                       │  /api/*  ──►  api (FastAPI, uvicorn, non-root, read-only filesystem)
                       │  /api/health* → 404 from outside (orchestrator calls the API directly)
                     worker (python -m app.worker: unpaid-order expiry, outbox e-mails) — no network port
                     postgres (one database + role per store; never published) ── daily backup → encrypted offsite copy
```

Files: `deploy/docker-compose.prod.yml`, `deploy/Dockerfile.api` (API + worker), `deploy/Dockerfile.web` (builds both
storefronts into Caddy), `deploy/Caddyfile`, `deploy/production.env.example`, `deploy/backup-offsite.{service,timer}`.
`docker compose -f deploy/docker-compose.prod.yml config` validates (checked); the images have **not** been built here.
Scaling out later: several `api` instances behind Caddy work as-is (sessions and rate-limit state need a shared store
first — the in-process rate limiter is per instance); several workers are safe by design (row leases, advisory locks).

## 2. What you must supply (blockers)

| Item | Why |
|---|---|
| A server (VM) with Docker, a deploy user, firewall allowing 80/443 only, SSH by key | hosting |
| Two domain names + DNS records pointing at it; an e-mail for certificate notices | HTTPS (Let’s Encrypt via Caddy) |
| `APP_SECRET_KEY` and three database passwords (generate: `openssl rand -base64 48`) | secrets |
| An offsite storage target (S3-compatible bucket via rclone mount, NAS, …) and the backup encryption key, stored apart from the backups | offsite backups |
| An e-mail provider account (SMTP relay) and a sending domain with SPF, DKIM, DMARC | order and password e-mails |
| The business information in `docs/business-information.md` (identity, address, policies, prices) | legal / customer-facing content |
| Decision on the AI model host (a private Ollama server) or `LLM_ENABLED=false` (the rule-based assistant) | assistant |
| Authorisation to deploy publicly | — |

Payment-provider integration is out of scope: production would run the **sandbox** provider, i.e. no real orders can be
paid. Do not launch commercially before a real provider is integrated and reviewed.

## 3. Secrets management

`/etc/avc/production.env` (from `deploy/production.env.example`), mode 600, owned by the deploy user, never in Git; the
backup key in `/etc/avc/backup.key` (mode 600) **and** in a password manager. Settings never print secrets (`repr=False`
fields, redacting log filter). Rotate `APP_SECRET_KEY` to force every session to re-authenticate; rotate database
passwords with `ALTER ROLE … PASSWORD` + env update + restart. A managed secrets store (cloud KMS / Vault) can replace the
env file without code changes (the app reads environment variables only).

## 4. First deployment

1. Server prepared (§2). `git clone` the reviewed commit to `/opt/ai-voice-commerce`; create `/etc/avc/production.env`.
2. `AVC_ENV_FILE=/etc/avc/production.env docker compose -f deploy/docker-compose.prod.yml --env-file /etc/avc/production.env up -d --build postgres`
3. Schema on the empty databases (fresh install, no backup needed):
   `docker compose … run --rm api python -m app.migrate --apply`. Then load the real catalogue/policies (not the demo
   seed: `app.seed` creates synthetic data and demo accounts).
4. `docker compose … up -d --build` (api, worker, web). Check `https://<domain>/` and, from the host,
   `docker compose … exec api python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/api/health').read())"`.
5. Enable `deploy/backup-offsite.timer`; run it once by hand and check `scripts/backup_offsite.sh --verify …`.

## 5. Updates and rollback

* **Update:** backup → `python -m app.migrate --plan --backup …` → `--apply …` (migrations are additive / expand-contract,
  so the running old code keeps working) → rebuild and restart `api`, `worker`, `web`. The API refuses to start if a
  migration is pending, so a missed step fails loudly instead of serving errors.
* **Roll back code:** check out the previous commit and rebuild; additive migrations need no rollback.
* **Roll back a migration** only when the new schema itself is the problem: its guarded `backend/migrations/down/*.sql`
  (refuses to lose data unless explicitly allowed after a verified backup), per store, after a backup.
* **Restore data:** `docs/database-safety.md` → Recovery (restore into a replacement database, verify, then cut over).

## 6. Monitoring, logs and alerts

* Probes: `/api/health/live` (process), `/api/health/ready` (both databases; 503 removes the instance), `/api/health`
  (detail: databases, payments mode, LLM, policy warnings, worker state) — internal only.
* Logs: `LOG_FORMAT=json` → one JSON object per line with request id, status and duration; secrets are redacted. Ship
  them with the host's collector (journald / Docker logging driver → Loki, CloudWatch, …).
* Alert on: readiness failing; `background.<store>.outbox_dead > 0`; oldest pending outbox item > 15 min;
  `jobs.expire_unpaid.last_succeeded_at` older than 30 min; 5xx rate; certificate expiry (Caddy renews automatically);
  backup timer failure or a `--verify` failure.
* Error monitoring: errors are logged with the exception (redacted). An external error tracker (Sentry, …) is an
  optional add-on that needs an account; it is not configured.

## 7. E-mail delivery

`notify.py` sender abstraction: `dev_outbox` (development: files in `.run/outbox/`), `smtp` (production: any SMTP relay;
STARTTLS or implicit TLS required; credentials from `SMTP_*`), `none`. Order-shipped e-mails go through the worker’s
outbox (retries, dead-letter); password-reset e-mails are sent inline. **No provider is enabled** — it needs an account,
a verified sending domain and your approval.

## 8. Security review (Phase J)

Done in this phase:

| Area | State |
|---|---|
| Transport | HTTPS only (Caddy, HSTS, `upgrade-insecure-requests`); API adds HSTS in production |
| Sessions | Server-side sessions with revocation; sign-out, **sign-out everywhere** (`/auth/logout-all`), password reset revokes all; expiry `TOKEN_TTL_MINUTES` |
| Cookies | `AUTH_COOKIES=true` (production): HttpOnly, Secure, SameSite=Strict, scoped to each store’s API path; token never given to page scripts |
| CSRF | Double-submit token on every state-changing cookie request (`X-CSRF-Token`), constant-time compare; bearer mode is CSRF-immune |
| Headers | API: strict CSP, nosniff, DENY framing, no-referrer, no-store on private data; storefront: CSP `'self'` only, microphone limited to the page itself |
| Authorisation | All 40 routes inventoried: staff routes need an agent of that store, shopping/payment a customer, order data a signed-in owner; cross-store tokens 403; every route rate-limited |
| Input | Strict request schemas (unknown fields rejected); staff fields validated (https-only tracking links); India address rules |
| Data | Store isolation by database + role; no internal ids in responses; staff notes never shown to customers |
| Secrets | Not in Git (scan of all 99 changed files: clean), not in logs, not in reprs |
| Backups | Encrypted offsite copies with HMAC authentication and decrypt-and-verify (tamper and wrong-key detection tested) |
| Containers | Non-root, read-only filesystem, no-new-privileges; database never published |

Open items (not done): dependency vulnerability audit (`pip-audit`, `npm audit` need network access to advisory
databases — run them in CI), penetration test, a shared rate-limit store for multiple API instances, Content-Security-
Policy reporting endpoint, WAF / DDoS protection at the edge, legal pages, and a real payment provider with its own
security review.

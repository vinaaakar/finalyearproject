# Security: development vs production

## What the code now enforces

| Area | Development (`APP_ENV=development`) | Production / any other `APP_ENV` |
|---|---|---|
| API docs `/docs` `/redoc` `/openapi.json` | on | **off** (404) unless `API_DOCS_ENABLED=true` |
| Phone simulator | on | **off** (404) unless `PHONE_SIMULATOR_ENABLED=true` |
| Demo seeding `python -m app.seed` | allowed | **refused** (published demo passwords) unless `--allow-demo-data`; `--reset` always refused |
| Demo credentials on the sign-in page | shown (Vite dev build) | **not in the bundle** (`import.meta.env.DEV`; verified by grepping `dist/`) |
| HSTS | not sent (plain http) | `Strict-Transport-Security: max-age=31536000; includeSubDomains` |
| Client identity (rate limits, phone limits) | peer address | peer address; `X-Forwarded-For` used **only** from `TRUSTED_PROXIES` |

Headers on every API response (including 4xx/5xx): `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()`,
`Cross-Origin-Opener-Policy: same-origin`, `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none';
form-action 'none'` (the dev-only docs page is exempt), and `Cache-Control: no-store` on anything personal (auth, account,
orders, cart, checkout, chat, payments, speech, phone, or any request with a bearer token). Unhandled errors return a generic
500 body with the same headers. Tests: `backend/tests/test_phase1_1_security.py`.

## Storefront pages (not served by the API)

Vite serves them in development; in production the web host/CDN must send:
```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;
  media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'
  (+ checkout.razorpay.com / api.razorpay.com in script-src, frame-src and connect-src once Razorpay is added)
Permissions-Policy: microphone=(self), camera=(), geolocation=(), payment=(self)
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
```
The voice assistant needs `microphone=(self)`. These are deployment settings; no Vite configuration was changed (changing
`vite.config.js` restarts the dev servers).

## Sessions: current design and the migration to cookies

Today: an HMAC-signed bearer token bound to a server-side session row (revocable), kept in `sessionStorage` and sent in the
`Authorization` header. Consequences:
- **CSRF**: not applicable today — browsers never attach the token automatically, and CORS allows only the storefront origins.
- **XSS**: any script running on the storefront could read the token. The production CSP above is the main mitigation.

Moving to an httpOnly cookie removes token theft by XSS but **introduces CSRF**, so it must be done as one change:
1. `POST /auth/login` sets `__Host-avc_session_<store>` (`HttpOnly; Secure; SameSite=Lax; Path=/`), value = the same session id
   (still hashed server-side). Separate cookie per store keeps Store A and Store B sessions isolated.
2. CSRF: double-submit token (a non-httpOnly `avc_csrf` cookie echoed in an `X-CSRF-Token` header on every state-changing
   request) **and** an `Origin`/`Sec-Fetch-Site` check against the store's origin.
3. Transition: accept both bearer and cookie for one release, then remove bearer support; sign-out clears the cookie.
4. Requires HTTPS everywhere (`Secure`, `__Host-`), and the API and storefront on the same site (reverse proxy) so the cookie is
   first-party. No database change (sessions table already exists).
Not implemented in Phase 1.1 because it changes the authentication architecture.

## Rate limiting

In-memory sliding windows per client (and per bucket). Behind a reverse proxy set `TRUSTED_PROXIES` to the proxy address(es),
otherwise all clients share one budget. Limits reset on restart and are not shared across instances; a multi-instance
deployment needs a shared store (Redis), which is an infrastructure decision. The phone-verification guard has the same
limitation (documented in `app/phone/session.py`).

## Remaining items (need decisions or infrastructure)
- httpOnly-cookie sessions + CSRF (above).
- Shared rate-limit / phone-guard store for multiple instances.
- Production web-host headers (above) and HTTPS.
- Remove or rotate the seeded demo accounts in any environment that was ever seeded.

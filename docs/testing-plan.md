# Frontend and browser testing plan (dependencies NOT installed — needs approval)

Current state: 0 frontend tests; backend 439 pytest tests; 47 script tests; `scripts/eval_llm.py` (local model, opt-in).
Environment: Node 25.6.1, npm 11.18, Vite 5.4.11, React 18.3.1, `frontend/node_modules` 44 MB, 13 GB free, Google Chrome installed.

## Proposed dev dependencies (frontend workspace root, exact pins; re-check the latest patch of each at install time)

| Package | Version | Purpose | Approx. size |
|---|---|---|---|
| `vitest` | 2.1.8 | Unit/component test runner (Vite 5 compatible) | ~15 MB |
| `jsdom` | 25.0.1 | DOM for component tests | ~10 MB |
| `@testing-library/react` | 16.1.0 | Render components, query by role/label | <1 MB |
| `@testing-library/dom` | 10.4.0 | Peer of the above | <1 MB |
| `@testing-library/user-event` | 14.5.2 | Realistic clicks/typing (double-click tests) | <1 MB |
| `@testing-library/jest-dom` | 6.6.3 | DOM assertions | <1 MB |
| `@playwright/test` | 1.49.1 | Browser tests | ~10 MB |
| `@axe-core/playwright` | 4.10.1 | Accessibility checks in browser tests | ~3 MB |

Playwright browsers: **not downloaded** — tests run with `channel: 'chrome'` against the installed Google Chrome. If you
prefer Playwright's pinned Chromium, `npx playwright install chromium` downloads ~150 MB (separate approval).
Total ≈ 40–60 MB added to `node_modules`. No runtime (production bundle) dependencies change.

## Tests to write after approval

Component (Vitest + Testing Library, API mocked):
- PaymentPage: "Cancel this order" shows the confirmation (what will happen, order number); "Keep my order" closes it;
  confirm calls `cancelOrder` once even on double click; success shown only when the response status is `cancelled`;
  an API error is shown and the order stays as it was; a 409 `already_cancelled` message is displayed.
- ChatWidget: cancel-order action needs a second click; add-to-cart reports success only after the API succeeds; Tamil
  default UI; language selector; no demo credentials rendered when `import.meta.env.DEV` is false.
- CheckoutPage: one idempotency key per review; 409 refreshes the quote; button disabled while placing.

Browser (Playwright, against an isolated API on the *_test databases and `vite preview` builds on spare ports — never the
dev stack): register → browse → search "backpack" → cart → checkout → sandbox pay → order → ask Scout/Maple → confirmed
cancel of an unpaid order; double-click "Place order" creates one order; 390/820/1366 px; keyboard-only path; axe scan;
response headers present on API calls; production build has no demo credentials.

Already covered without new dependencies (this phase): security headers, docs gating, phone lockout tiers and exact time
windows with a mocked clock, catalogue verification beyond 200 products, database tooling with a fake Docker, and the
fixed-prompt local model evaluation (`scripts/eval_llm.py`: 7/8 model policy replies accepted, all trust invariants held).

# Phase 2 safety test scenarios (design — implemented together with the features they protect)

These are **pytest** tests (no new dependencies) against the `*_test` databases. "Mock RZP" = a local fake Razorpay HTTP
server (recorded response shapes, signatures computed with test secrets); no real Razorpay call is ever made. References are
to `docs/india-razorpay-design.md` (RZP §) and `docs/migration-runner-safety.md` (MRS §).

## Payment safety (RZP §7.3, §7.5–7.7)

| # | Scenario | Setup | Action | Expected database state | Customer-visible result | Mock RZP |
|---|---|---|---|---|---|---|
| P1 | Two attempts captured concurrently | Order `pending_payment`; attempts A1, A2 on two provider orders | Settle a capture for A1 and A2 in two parallel threads | Exactly one `provider_payments.is_accepted`; the other captured row `is_accepted=false` with one `refunds` row `required` (`auto-surplus:<id>`); order `processing`; the unique index never violated | "Payment confirmed"; "extra payment … will be refunded" | Yes |
| P2 | Old attempt captured late | A1 marked `failed`, A2 captured and accepted | Settle a late capture for A1 | A1's provider row `captured`, not accepted; refund `required` for its amount; A2 unchanged; order not touched | "Extra payment of ₹X will be refunded" | Yes |
| P3 | Duplicate capture webhook | One capture already applied | Deliver the same event id twice, then a new event id for the same capture | One `payment_events` row per event id; second delivery returns 200 with no change; second event id → `ignored` | Unchanged | Yes |
| P4 | Duplicate refund request | Captured ₹1000 | `request_refund(key K, ₹400)` twice | One refunds row for K; the second call returns the same row | One refund shown | No (DB only) |
| P5 | Refund exceeds captured | Captured ₹1000, completed refund ₹700 | Request ₹400 | Rejected `RefundExceedsCaptured`; no row inserted | Staff sees "exceeds refundable ₹300" | No |
| P6 | Two concurrent partial refunds | Captured ₹1000 | Two threads request ₹600 each (different keys) | Exactly one row inserted; the other rejected (lock serialises; Σ never > ₹1000) | One refund in progress | No |
| P7 | Automatic authorisation expiry | Attempt `authorized`, order cancelled | Mock reports the payment uncaptured after the window; run reconciliation | Provider row `expired`; attempt `expired`; **no** refunds row; order stays cancelled | "Amount held is being released automatically (5–7 working days)" | Yes |
| P8 | Capture after order cancellation | Order cancelled (customer or expiry) | Settle a capture | Provider row captured, not accepted; refund `required`; order stays `cancelled` (never revived); outbox alert row | "Extra payment will be refunded" | Yes |
| P9 | Refund failure then retry | Refund K `pending` | Mock returns `failed`; staff retries | K → `failed` (terminal, amount back in balance); new row K2 with a new receipt; K2 sent; mock `processed` → K2 `completed` | "Refund failed, retrying" → "Refund completed ₹X on <date>" | Yes |
| P10 | Refund timeout and duplicate receipt | Refund K `approved` | Mock times out after creating the refund; retry gets "Duplicate receipt" | K stays one row, `provider_refund_id` attached by listing refunds and matching the receipt; never a second refund | "Refund in progress" | Yes |
| P11 | Amount/store mismatch | Mock payment amount ≠ attempt amount | Settle | Not accepted; `orders.needs_review` set; event `invalid` (if webhook) | "Payment under review" | Yes |
| P12 | Sandbox refund isolation | Production settings | Request a `kind='sandbox'` refund | Refused | n/a | No |
| P13 | Derived refund status | Captured ₹1000 with refunds: completed ₹300, pending ₹200, failed ₹500 | Read `provider_payment_refund_summary` and the assistant answer | refunded 300, in_flight 200, refundable 500 (failed counts 0); no refund state stored on `provider_payments` | "Refund in progress (₹200)"; "₹300 refunded on <date>" — never "fully refunded" | No |
| P14 | Capture before the window ends | Attempt `authorized`, order `pending_payment`, window ends in < 10 min | Run `capture_before_window` | Capture API called once (mock); settlement accepts it; order `processing` | "Payment confirmed" | Yes |
| P15 | Refund made in the Razorpay dashboard | Captured payment; mock lists a refund we did not create | Run reconciliation | New refunds row `origin='external'` with the provider status; balance reduced | Refund shown truthfully | Yes |
| P16 | Live keys refused outside production | `APP_ENV=development`, live-mode configuration | Start the app | Startup refused (config error) | n/a | No |

## Webhook safety (RZP §7.4)

| # | Scenario | Setup | Action | Expected database state | Customer-visible result | Mock RZP |
|---|---|---|---|---|---|---|
| W1 | Duplicate event id | Event E applied | POST E again | Still one row for E (`applied`); response 200; no state change | Unchanged | Signed payload only |
| W2 | Out-of-order events | Capture applied | POST `payment.authorized` for the same payment | New event row `ignored`; payment stays captured | Unchanged | Signed payload only |
| W3 | Invalid signature | — | POST with a wrong signature, and with a valid signature over a different body | 400; no `payment_events` row; nothing changed | n/a | Signed payload only |
| W4 | Slow downstream processing | Outbox worker paused | POST a capture | Response < 1 s with 200; state applied; outbox row pending; worker later processes it | Payment confirmed immediately; email later | Signed payload only |
| W5 | Provider retry after failure | Inject a lock timeout during settlement | POST E (→ 503), then POST E again | After the first: no `payment_events` row for E, one `payment_event_failures` row; after the second: E `applied` | Confirmed after the retry | Signed payload only |
| W6 | Crash between receipt and state update | Kill the transaction after the event INSERT, before COMMIT (fault injection) | Then redeliver E | Nothing from the first attempt persisted; redelivery applies once | Confirmed after the retry | Signed payload only |
| W7 | Permanently invalid event | Unknown provider order id / other store | POST | Row `invalid` with detail; 200 (no endless retries); no money state change | n/a | Signed payload only |
| W8 | Webhook lost entirely | No webhook delivered | Run reconciliation | Capture settled via `GET /v1/orders/{id}/payments`; delivery-lag alert recorded | Confirmed after reconciliation | Yes |

## Migration safety (MRS §3, RZP §4.3)

| # | Scenario | Setup | Action | Expected database state | Customer-visible result | Mock RZP |
|---|---|---|---|---|---|---|
| M1 | Historical checksum mismatch | Applied 0002 recorded; file edited by one byte | `migrate --plan` and real run | Refused before any change; message names version and both hashes | None | No |
| M2 | Two runners at once | Runner 1 holds the advisory lock (paused) | Start runner 2 | Runner 2 waits then times out; no partial work; holder named | None | No |
| M3 | Lock timeout during DDL | Another session holds `ACCESS EXCLUSIVE`-blocking lock on a table | Apply a migration touching it | `SET LOCAL lock_timeout` aborts; that migration rolled back; run stops | No blocked customer requests | No |
| M4 | Failed precheck | Backup older than 24 h / stores divergent / backup checksum bad | Real run | Refused; no change | None | No |
| M5 | Store A succeeds, Store B fails | Data in B violates the new migration's constraint | Real run | A at V, B at V−1 (exactly one apart); run log records the failure | Both stores keep working (backward compatible) | No |
| M6 | Restart after partial migration | State from M5 | Normal run, then fix data and `--repair` | Normal run refused; `--repair` applies V to B only; both at V | None | No |
| M7 | Invalid rollback refused | 0006 applied; one `provider_payments` row exists (or an `authorized` payment, or unprocessed outbox) | Run the 0006 down script | Exception raised; schema and data unchanged | None | No |
| M8 | Valid rollback | 0006/0007 applied, no financial rows | Run 0007 down then 0006 down | Old schema restored; `schema_migrations` rows removed | None | No |
| M9 | Linted migration | A migration file containing `COMMIT` or `CREATE INDEX CONCURRENTLY` | `--plan` | Refused | None | No |

## Recovery (docs/database-safety.md, Recovery)

| # | Scenario | Setup | Action | Expected | Mock RZP |
|---|---|---|---|---|---|
| R1 | Ownership-preserving restore (rehearsal on a scratch name; **creates and drops a database — needs approval each time it is run**) | Verified backup | Stage 1 steps 1–4 against `store_a_test`'s dump into a scratch name | All verification queries pass (owners, sequences, FKs, counts, versions) | No |
| R2 | Restore-check limits | — | Assert the restore-check output claims counts only | No ownership/sequence claim is printed | No |

## Worker / scheduler (docs/scheduler-architecture.md)

| # | Scenario | Setup | Action | Expected | Mock RZP |
|---|---|---|---|---|---|
| S1 | Two workers, one outbox | 20 pending outbox rows | Run two workers concurrently | Every row processed exactly once (`SKIP LOCKED` + lease) | Yes (refund sends) |
| S2 | Periodic job singleton | Worker 1 holds the `reconcile` advisory lock | Worker 2 reaches the same job | Worker 2 skips it; `job_runs` shows one run | Yes |
| S3 | Worker killed mid-row | Row claimed, process killed | Wait past `locked_until`, run again | Row reclaimed and processed once (idempotent handler) | Yes |
| S4 | Backoff and dead letter | Handler always fails | Run repeatedly with a fake clock | `available_at` grows 2^n minutes (capped 6 h); after 10 attempts `status='dead'` and an alert | No |
| S5 | Stale reconcile signal | `job_runs.reconcile.last_succeeded` 31 min old | Read health | Health reports the stale job | No |

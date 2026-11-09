# India-first commerce and Razorpay (test mode): technical design

Status: **proposal for review, revision 3 (Phase 1.2A). Nothing in this document is implemented.** It needs your approval
because it changes database schemas and data, adds an external integration (Razorpay) and needs test credentials.

Revision 3 fixes the Phase 1.2 audit findings F2–F9 (order-level capture invariant, one refund authority, refunds always
tied to a payment, authorisation expiry, refund idempotency via receipt, webhook deadline, webhook outcome, safe rollback of
0006/0007) and incorporates the Razorpay documentation checked in Phase 1.2.

**Labels used throughout:** **[CONFIRMED]** = stated in Razorpay's official documentation (sources in §10);
**[DECISION]** = our design choice; **[ASSUMPTION]** = not confirmed, must be verified before implementation.
**Sandbox vs Razorpay:** today only the sandbox provider exists (`payments` + `sandbox_payment_intents`, no real money).
Everything in §7 applies to the Razorpay provider only; the sandbox keeps its current behaviour and never writes
`provider_payments`. Live Razorpay keys are refused outside production (§7.0).

Related documents: `docs/migration-runner-safety.md` (how 0004–0007 will be applied), `docs/scheduler-architecture.md`
(reconciliation/expiry jobs), `docs/testing-plan.md` (tests for every requirement below), `docs/database-safety.md`
(backup and recovery), `docs/security.md`.

## 1. Current coupling (what has to change)

| Area | Where | Assumption today |
|---|---|---|
| Address validation | `schemas.ShippingAddress` | `country: Literal["US"]`; `region` must be a US state code; `postal_code` `^\d{5}(-\d{4})?$` |
| Region list | `stores.US_REGIONS`, `frontend/.../CheckoutPage.jsx` (`STATES`) | Hard-coded US states, duplicated front and back |
| Shipping eligibility | `stores.SHIPPING_EXCLUDED_REGIONS`, `commerce.validate_address`, `care.py` (Alaska/Hawaii text) | Python constants, not store data |
| Shipping rates | `store_profile.standard_shipping_cents / free_shipping_min_cents / expedited_shipping_cents` | One flat national rate per store |
| Currency | `store_profile.currency CHAR(3) DEFAULT 'USD'`; `commerce.money()` and `assistant/service.money()` print `$`; `_MONEY_RE` and grounding understand `$` | Single currency, `$` formatting, no currency on `orders` |
| Amounts | `*_cents` columns | Integer minor units (good: paise fit unchanged) |
| Phone verification | `phone/session.py` | "five-digit ZIP code" |
| Policy text | `seed.py`, `policy_translations.py`, `policies` rows | US rates, US-only shipping, US time zones (MT/ET), USD amounts |
| Payments | `payments/base.py` protocol + `sandbox.py` | Provider-independent already; no webhook path, no event store, no provider order id |

## 2. Decisions needed from you first

1. **Repricing:** INR prices for every product (a business decision, not a currency conversion). Supply the price list or approve a
   one-off repricing table. No exchange-rate conversion will be applied automatically.
2. **Existing synthetic orders** (USD): keep them as historical USD orders (recommended; `orders.currency='USD'`), or reset the demo data.
3. **Shipping zones and rates** per store (e.g. metro / rest of India / North-East & islands), free-shipping thresholds, delivery estimates.
4. **Payment methods to enable in Razorpay test mode** (cards, UPI, netbanking, wallets). COD is out of scope unless you decide otherwise.
5. **Business identity** for policies, invoices and Razorpay: legal name, GSTIN (if any), grievance officer contact, support phone/email, hours (IST).

## 3. Schema changes (migrations 0004–0007, expand/contract)

Every migration is additive and backward compatible with the code running before it (§4), and is applied by the hardened
runner described in `docs/migration-runner-safety.md`. Each ships with a guarded down script (§4.3).

```sql
-- 0004_geography.sql ------------------------------------------------------------------------------------------
CREATE TABLE countries (code CHAR(2) PRIMARY KEY, name TEXT NOT NULL, postal_pattern TEXT NOT NULL, enabled BOOLEAN NOT NULL DEFAULT false);
CREATE TABLE regions (country CHAR(2) NOT NULL REFERENCES countries(code), code TEXT NOT NULL, name TEXT NOT NULL,
                      kind TEXT NOT NULL CHECK (kind IN ('state','union_territory')), PRIMARY KEY (country, code));
-- seed: IN (^[1-9][0-9]{5}$) with 28 states + 8 union territories (ISO 3166-2:IN); US kept for historical orders, disabled.

-- Zones are rows, not arrays, so every rule is referentially checked and overlaps can be prevented (correction 7).
CREATE TABLE shipping_zones (id SERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, country CHAR(2) NOT NULL REFERENCES countries(code),
    standard_minor INTEGER NOT NULL CHECK (standard_minor >= 0), free_over_minor INTEGER CHECK (free_over_minor >= 0),
    express_minor INTEGER CHECK (express_minor >= 0), eta_min_days SMALLINT NOT NULL CHECK (eta_min_days >= 0),
    eta_max_days SMALLINT NOT NULL, active BOOLEAN NOT NULL DEFAULT true, CHECK (eta_max_days >= eta_min_days));
CREATE TABLE shipping_zone_regions (zone_id INTEGER NOT NULL REFERENCES shipping_zones(id) ON DELETE CASCADE,
    country CHAR(2) NOT NULL, region_code TEXT NOT NULL, FOREIGN KEY (country, region_code) REFERENCES regions(country, code),
    PRIMARY KEY (zone_id, country, region_code), UNIQUE (country, region_code));          -- a state belongs to ONE zone
CREATE TABLE shipping_zone_pins (zone_id INTEGER NOT NULL REFERENCES shipping_zones(id) ON DELETE CASCADE,
    pin_prefix TEXT NOT NULL CHECK (pin_prefix ~ '^[1-9][0-9]{0,5}$'), PRIMARY KEY (zone_id, pin_prefix),
    UNIQUE (pin_prefix));                                                                  -- a prefix belongs to ONE zone
-- Resolution order (code, tested): longest matching PIN prefix → state zone → not deliverable. An admin check rejects
-- a prefix that is a prefix of another zone's prefix with a different zone (e.g. '11' in zone A and '110' in zone B is
-- allowed only if documented as an intentional override — the longest match wins deterministically).

-- 0005_currency.sql (expand) — backward compatible with today's checkout code (correction 2, 6) -----------------
ALTER TABLE orders   ADD COLUMN currency CHAR(3) NOT NULL DEFAULT 'USD';    -- existing rows = historical USD; old code still inserts
ALTER TABLE products ADD COLUMN currency CHAR(3) NOT NULL DEFAULT 'USD';
ALTER TABLE orders ADD COLUMN shipping_phone TEXT, ADD COLUMN shipping_landmark TEXT,
                   ADD COLUMN shipping_zone_id INTEGER REFERENCES shipping_zones(id);
-- Later (contract, after the INR price list is approved and the new code that writes currency is deployed):
--   UPDATE products SET price_cents = <approved INR price>, currency = 'INR' …   (previous values kept in products_backup_0005)
--   ALTER TABLE orders ALTER COLUMN currency DROP DEFAULT;          -- new code must state the currency explicitly
--   ALTER TABLE products ADD CONSTRAINT products_store_currency CHECK (currency = 'INR');   -- one currency per store catalogue
-- Checkout additionally refuses any cart whose product currency differs from store_profile.currency.

-- 0006_payment_attempts.sql [DECISION] (F2, F5, F8) ----------------------------------------------------------
-- Local `payments` row = one checkout attempt = one Razorpay order (a Razorpay order can receive several payment
-- attempts [CONFIRMED], each recorded in provider_payments).
ALTER TABLE payments ADD COLUMN provider_order_id TEXT UNIQUE;                 -- Razorpay order_…
ALTER TABLE payments DROP CONSTRAINT payments_status_check;
ALTER TABLE payments ADD CONSTRAINT payments_status_check CHECK (status IN
    ('pending','authorized','succeeded','failed','cancelled','expired','superseded'));
DROP INDEX payments_one_active_per_order;
CREATE UNIQUE INDEX payments_one_active_per_order ON payments (order_id) WHERE status IN ('pending','authorized','succeeded');

-- Every provider payment attempt, tied to BOTH its local attempt and its order (F2). No refund states here (F3).
CREATE TABLE provider_payments (
    id                  SERIAL PRIMARY KEY,
    order_id            INTEGER NOT NULL REFERENCES orders(id),
    payment_id          INTEGER NOT NULL REFERENCES payments(id),
    provider            TEXT NOT NULL,
    provider_payment_id TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN ('created','authorized','captured','failed','expired')),
                        -- 'expired' = authorised, never captured, released by the provider after the capture window (F5);
                        -- it is NOT a refund and never gets a refunds row.
    is_accepted         BOOLEAN NOT NULL DEFAULT false,   -- this capture is THE payment for the order
    amount_minor        INTEGER NOT NULL CHECK (amount_minor >= 0),
    currency            CHAR(3) NOT NULL,
    method              TEXT,
    failure_reason      TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_payment_id),
    CHECK (NOT is_accepted OR status = 'captured')
);
-- THE ORDER-LEVEL CAPTURE INVARIANT (F2): at most one accepted capture per order, enforced by the database.
CREATE UNIQUE INDEX provider_payments_one_accepted_per_order ON provider_payments (order_id) WHERE is_accepted;
CREATE INDEX provider_payments_order_idx ON provider_payments (order_id);

ALTER TABLE orders ADD COLUMN needs_review TEXT;   -- set with a reason when reconciliation finds an inconsistency

-- Webhook events (F7, F8): the provider event id makes delivery idempotent [CONFIRMED: x-razorpay-event-id].
CREATE TABLE payment_events (
    id            BIGSERIAL PRIMARY KEY,
    provider      TEXT NOT NULL,
    event_id      TEXT NOT NULL,
    event_type    TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('processing','applied','ignored','invalid')),
    detail        TEXT,
    payload_sha256 TEXT NOT NULL,
    received_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at  TIMESTAMPTZ,
    UNIQUE (provider, event_id),
    CHECK ((status = 'processing') = (processed_at IS NULL))
);
-- Slow follow-ups (emails, staff alerts, refund sending) are queued here in the SAME transaction as the state change and
-- processed by the background worker (docs/scheduler-architecture.md). Rows are never deleted while unprocessed.
CREATE TABLE outbox (id BIGSERIAL PRIMARY KEY, kind TEXT NOT NULL, payload JSONB NOT NULL, available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_until TIMESTAMPTZ,                       -- lease held by a worker while it processes the row
    attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done','dead')),   -- dead = gave up after max attempts (alerted)
    processed_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX outbox_pending_idx ON outbox (available_at) WHERE status = 'pending';
-- Last run of each periodic job (reconcile, expire, outbox), for monitoring and the health endpoint.
CREATE TABLE job_runs (job TEXT PRIMARY KEY, last_started TIMESTAMPTZ, last_succeeded TIMESTAMPTZ, last_error TEXT,
    last_error_at TIMESTAMPTZ);
-- Retryable failures roll back the event row (§7.4); they are counted here, outside that transaction, for monitoring.
CREATE TABLE payment_event_failures (id BIGSERIAL PRIMARY KEY, provider TEXT NOT NULL, event_id TEXT, error_class TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now());

-- 0007_refunds.sql [DECISION] (F3, F4, F6) ----------------------------------------------------------------------
-- The ONLY authority for refund state.
CREATE TABLE refunds (
    id                  SERIAL PRIMARY KEY,
    order_id            INTEGER NOT NULL REFERENCES orders(id),
    kind                TEXT NOT NULL CHECK (kind IN ('provider','sandbox')),
    provider_payment_id INTEGER REFERENCES provider_payments(id),   -- required for provider refunds (F4)
    sandbox_payment_id  INTEGER REFERENCES payments(id),            -- required for sandbox refunds (no real money)
    amount_minor        INTEGER NOT NULL CHECK (amount_minor > 0),
    currency            CHAR(3) NOT NULL,
    status              TEXT NOT NULL CHECK (status IN ('required','requested','approved','pending','completed','failed','rejected')),
    reason              TEXT NOT NULL,
    request_key         TEXT NOT NULL UNIQUE,      -- our idempotency key for the refund REQUEST
    receipt             TEXT NOT NULL UNIQUE,      -- derived from request_key, sent to Razorpay (F6)
    provider_refund_id  TEXT UNIQUE,
    origin              TEXT NOT NULL CHECK (origin IN ('application','external')),  -- external = done in the Razorpay dashboard
    created_by          INTEGER REFERENCES customers(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((kind = 'provider') = (provider_payment_id IS NOT NULL)),
    CHECK ((kind = 'sandbox')  = (sandbox_payment_id IS NOT NULL))
);
CREATE INDEX refunds_provider_payment_idx ON refunds (provider_payment_id);
CREATE INDEX refunds_order_idx ON refunds (order_id);

-- Derived refund status (F3): never stored, always computed from refunds.
CREATE VIEW provider_payment_refund_summary AS
SELECT pp.id AS provider_payment_id, pp.order_id, pp.amount_minor AS captured_minor,
       COALESCE(SUM(r.amount_minor) FILTER (WHERE r.status = 'completed'), 0) AS refunded_minor,
       COALESCE(SUM(r.amount_minor) FILTER (WHERE r.status IN ('required','requested','approved','pending')), 0) AS in_flight_minor
FROM provider_payments pp LEFT JOIN refunds r ON r.provider_payment_id = pp.id
WHERE pp.status = 'captured'
GROUP BY pp.id;
```

### 3.1 Derived refund status (F3) [DECISION]
For a captured provider payment: `refundable = captured − refunded − in_flight` (failed and rejected refunds count for nothing).

| Condition | Derived status shown to staff/customer |
|---|---|
| refunded = 0 and in_flight = 0 | not refunded |
| in_flight > 0 | refund in progress (amount = in_flight) |
| 0 < refunded < captured and in_flight = 0 | partially refunded (amount = refunded) |
| refunded = captured | fully refunded |

The order-level status sums all of the order's captured provider payments (an order can have an accepted capture plus a
surplus capture being refunded). A `failed` refund returns its amount to `refundable`; retrying it is a **new** refund
request (new `request_key` → new `receipt`), never a reuse of the failed row. The assistant's `truth.refund_evidence()`
reads this view: "refund completed" only for `completed` rows (amount and date from the row).

## 4. Migration and rollback strategy

### 4.1 Order and procedure
1. Use the hardened runner (`docs/migration-runner-safety.md`): checksums, advisory lock, enforced precheck, per-store
   transactions. Before running: `scripts/dbsafety.py precheck` Ready; `scripts/backup_db.sh`; approved restore-check.
2. **Expand → code → contract.** 0004–0007 only add things; defaults keep today's checkout working (an order inserted without
   `currency` gets `USD`). Then deploy code that writes currency, zones and provider rows. The contract step (drop defaults,
   currency CHECKs) is its own later migration with its own precheck and backup.
3. Test databases → scratch restore → dev databases, both stores.
4. Flags `STORE_A_MARKET` / `STORE_B_MARKET` (`US` | `IN`) switch address form, zones and currency display per store, so the
   first rollback step is a flag change.

### 4.2 Two-store failure
The runner migrates Store A, then Store B, each migration in one transaction per store. If Store B fails, Store A stays
migrated and Store B unchanged; because every step is backward compatible both keep working. The runner records the
failure and refuses further runs until both stores are at the same version (details and recovery in
`docs/migration-runner-safety.md` §5).

### 4.3 Guarded down scripts (F9)
Down scripts never run automatically. Each begins with a **refusal block** that checks the data first and raises an error
(leaving everything unchanged) if rolling back would lose or misrepresent money records:

```sql
-- down/0007_refunds.down.sql
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM refunds) THEN
    RAISE EXCEPTION 'refusing: refunds table has rows — refund records are financial history; fix forward instead';
  END IF;
END $$;
DROP VIEW provider_payment_refund_summary; DROP TABLE refunds;
DELETE FROM schema_migrations WHERE version = '0007_refunds';

-- down/0006_payment_attempts.down.sql (run only after 0007 is rolled back)
DO $$ BEGIN
  IF to_regclass('public.refunds') IS NOT NULL THEN RAISE EXCEPTION 'refusing: roll back 0007 first'; END IF;
  IF EXISTS (SELECT 1 FROM provider_payments) OR EXISTS (SELECT 1 FROM payment_events) THEN
    RAISE EXCEPTION 'refusing: Razorpay payment history exists; it cannot be represented in the old schema';
  END IF;
  IF EXISTS (SELECT 1 FROM outbox WHERE status <> 'done') THEN
    RAISE EXCEPTION 'refusing: unprocessed outbox work (emails/alerts/refund sends) would be lost';
  END IF;
  IF EXISTS (SELECT 1 FROM payments WHERE status IN ('authorized','expired','superseded')) THEN
    RAISE EXCEPTION 'refusing: payments in states the old schema does not allow (authorized/expired/superseded)';
  END IF;
END $$;
DROP INDEX payments_one_active_per_order;
CREATE UNIQUE INDEX payments_one_active_per_order ON payments (order_id) WHERE status IN ('pending','succeeded');
ALTER TABLE payments DROP CONSTRAINT payments_status_check;
ALTER TABLE payments ADD CONSTRAINT payments_status_check CHECK (status IN ('pending','succeeded','failed','cancelled'));
ALTER TABLE orders DROP COLUMN needs_review;
DROP TABLE job_runs; DROP TABLE outbox; DROP TABLE payment_event_failures; DROP TABLE payment_events; DROP TABLE provider_payments;
ALTER TABLE payments DROP COLUMN provider_order_id;
DELETE FROM schema_migrations WHERE version = '0006_payment_attempts';
```

**Safe rollback preconditions:** both checks above pass on that store; a fresh verified backup exists; the code that
writes the new tables is already switched off (flag) so no new rows appear during the rollback.
**Refused cases:** any refund row; any provider payment or webhook event; unprocessed outbox work; any payment
`authorized` / `expired` / `superseded`. In these cases rollback would destroy or misstate financial history, so the answer is a **forward fix**.
**Authorised payments** must first be settled: let reconciliation capture or let them expire (§7.3) until no local payment
is `authorized`. **Manual recovery** when a rollback is refused: keep the schema, fix the defect with a new forward
migration or code change; if the data itself is wrong, restore into a replacement database per `docs/database-safety.md`
(Recovery) and compare; never delete payment, refund or event rows by hand.

## 5. Currency handling

- Integer minor units (paise) everywhere, with a currency on products, orders, payments, provider payments and refunds.
  Totals are computed only from rows in the store's currency.
- One formatter `format_money(minor, currency)` replaces both `money()` copies (Indian grouping for INR: `₹1,24,999.00`).
- The assistant keeps the Phase 1 rule: budgets in another currency are explained, never converted. No exchange rates anywhere.

## 6. Indian address validation

- Fields: full name, mobile (`^(\+91[ -]?)?[6-9]\d{9}$`, stored E.164), line 1, line 2, landmark (optional), city,
  state/UT code (from `regions`), PIN (`^[1-9][0-9]{5}$`), country `IN`.
- Validated on the server from `countries`/`regions`; the storefront loads the same list from `/api/stores/{store}/regions`.
- Deliverable = a zone found by longest PIN prefix, else by state; otherwise "we don't deliver to this PIN yet".
- No external PIN lookup service unless you approve one. Phone verification asks for the 6-digit PIN.

## 7. Razorpay (test mode) integration

### 7.0 Configuration and the test-mode restriction [DECISION]
`.env` only (never in the frontend except the public key id): `PAYMENT_PROVIDER=razorpay`, `RAZORPAY_KEY_ID`,
`RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `RAZORPAY_CAPTURE_WINDOW_MINUTES` (default 30). Test and live keys are
separate [CONFIRMED]. Startup refuses live keys unless `PAYMENT_LIVE_AUTHORIZED=true` AND `APP_ENV=production`. The check
uses the key prefix `rzp_test_` / `rzp_live_` **[ASSUMPTION — the prefix is not stated on the pages read; verify]**; until
verified, the startup check also requires `RAZORPAY_MODE=test` to be set explicitly. HTTP via `httpx`; no SDK.

### 7.1 Order creation [DECISION]
`POST /orders/{n}/payments`, one transaction: lock the order (`FOR UPDATE`), require `pending_payment`, reuse an existing
`pending`/`authorized` local attempt (the unique index allows only one). Otherwise create the Razorpay order with amount in
paise from the database [CONFIRMED: smallest sub-unit], `currency='INR'`, `receipt=<order_number>` [CONFIRMED: ≤40 chars],
`notes={store, order_number}` [CONFIRMED: ≤15 pairs], an explicit automatic-capture setting and window (§7.3), then insert
the local attempt. If the provider call fails, nothing is inserted.

### 7.2 Checkout callback [CONFIRMED formula]
Verify `HMAC_SHA256(key_secret, order_id + "|" + razorpay_payment_id)` (hex) against `razorpay_signature`, using the
**order id stored on our server**, not the one returned by checkout [CONFIRMED]. Then fetch the payment from Razorpay
(server-side) and pass it to `settle_provider_payment` (§7.5). The browser's claim is never trusted by itself.

### 7.3 Authorisation and capture window (F5)
- [CONFIRMED] Automatic capture is the default; the auto-capture window can be set from 12 minutes to 3 days from creation,
  and values passed on the order override the dashboard. Authorised payments not captured within the window are
  **automatically refunded by Razorpay** (normal refund speed, typically 5–7 working days).
- [DECISION] Set the window explicitly on every order: `RAZORPAY_CAPTURE_WINDOW_MINUTES = 30`. Unpaid-order expiry is longer
  (`UNPAID_ORDER_TTL_MINUTES = 60`) so an order is never cancelled while its authorisation can still be captured.
- [DECISION] Reconciliation (§7.6) looks at every `authorized` provider payment: if Razorpay already captured it → settle;
  if the order is still `pending_payment` with no accepted capture and the window ends within 10 minutes → capture it via the
  Capture API [CONFIRMED that a Capture API exists; exact request **ASSUMPTION — verify**]; if the order is cancelled →
  do nothing and let the window pass.
- [DECISION] **Expired authorisations:** when Razorpay reports the payment uncaptured after the window (exact status label
  **[ASSUMPTION — verify; possibly `refunded` with no capture]**), set `provider_payments.status = 'expired'`, set the local
  attempt to `expired` if it has no other live provider payment, and **create no refunds row**. Our application never
  issues a refund for an uncaptured authorisation; refunds rows exist only for captured money.
- Customer-visible text for an expired authorisation: "Your payment of ₹X for order N was not completed. The amount held is
  being released automatically (typically 5–7 working days)."

### 7.4 Webhooks: fast, atomic, idempotent (F7, F8)
Facts [CONFIRMED]: signature header `X-Razorpay-Signature` = HMAC-SHA256 of the **raw** body with the webhook secret; event id
header `x-razorpay-event-id`, unique per event; delivery is at least once (duplicates expected) and may be out of order;
non-2xx or no response within **5 seconds** counts as failure; retries with exponential backoff for 24 hours, after which
the webhook is **disabled** and an alert email is sent.

```
POST /api/payments/razorpay/webhook                                   # target: respond well under 5 s
  raw = body (reject > 64 KB)
  if not constant_time_eq(hmac_sha256(WEBHOOK_SECRET, raw), header["X-Razorpay-Signature"]): return 400   # nothing stored
  event_id = header["x-razorpay-event-id"]; if missing: return 400
  event = json.loads(raw)                                              # parse only AFTER verification
  BEGIN  (SET LOCAL statement_timeout = '2s'; SET LOCAL lock_timeout = '1s')
    row = INSERT INTO payment_events(provider, event_id, event_type, status, payload_sha256)
          VALUES ('razorpay', event_id, event.type, 'processing', sha256(raw))
          ON CONFLICT (provider, event_id) DO NOTHING RETURNING id
    if row is None:                                                    # duplicate delivery of an event already committed
        COMMIT; return 200                                            # (applied / ignored / invalid) — nothing to do
    try:
        outcome, detail = settle_from_event(conn, event)              # §7.5, same function as callback/reconciliation
        UPDATE payment_events SET status = outcome, detail = detail, processed_at = now() WHERE id = row.id
        INSERT INTO outbox(...) for slow follow-ups (emails, staff alerts) — processed by the background worker
    except PermanentEventError as e:                                   # unknown provider order, wrong store, amount mismatch
        UPDATE payment_events SET status = 'invalid', detail = e.reason, processed_at = now() WHERE id = row.id
        UPDATE orders SET needs_review = e.reason WHERE id = e.order_id (if known)
    except RetryableError:                                             # lock timeout, database busy, bug
        ROLLBACK                                                       # event row disappears with the failed change
        record payment_event_failures(event_id, error_class)           # separate short transaction, for monitoring
        return 503                                                     # Razorpay retries (backoff, up to 24 h)
  COMMIT; return 200
```
- `processing` exists only inside the open transaction: a committed row is always `applied`, `ignored` or `invalid`
  (enforced by the CHECK on `processed_at`). A crash before COMMIT leaves nothing, and Razorpay retries; a crash after
  COMMIT but before the response makes Razorpay retry, and the retry is a no-op duplicate.
- **Out of order:** `settle_from_event` ranks provider-payment states `created < authorized < captured` (and `failed` only
  applies to a payment that is not captured). An older event arriving after a newer state is recorded as `ignored`.
- **No provider API calls inside the webhook** (they could exceed 5 s). The verified, signed payload is applied; the
  reconciliation job re-fetches from Razorpay and corrects anything later.
- **Monitoring:** alert when `payment_event_failures` grows, when reconciliation finds a captured payment that no webhook
  settled within 15 minutes (delivery lag), when no webhook arrives for N hours while payments are being created, and on
  Razorpay's "webhook disabled" email (configure the alert email address). Reconciliation is **mandatory**: payments must
  settle correctly even if every webhook is lost.

### 7.5 Settlement and the order-level capture invariant (F2)
One function, used by the checkout callback, webhooks and reconciliation. Locks are always taken in the same order —
**order → local attempts → provider payment** — so concurrent callers serialise per order and cannot deadlock.

```
def settle_provider_payment(conn, pp):              # pp = provider payment (fetched, or from a verified webhook)
    attempt_hint = SELECT order_id FROM payments WHERE provider_order_id = pp.order_id      # no lock yet
    if attempt_hint is None: raise PermanentEventError("unknown provider order")
    order   = SELECT * FROM orders WHERE id = attempt_hint.order_id FOR UPDATE              # 1. order lock
    attempt = SELECT * FROM payments WHERE provider_order_id = pp.order_id FOR UPDATE       # 2. the attempt
    if pp.notes.store != THIS_STORE: raise PermanentEventError("store mismatch")
    if (pp.amount, pp.currency) != (attempt.amount_cents, attempt.currency): raise PermanentEventError("amount mismatch")
    row = upsert provider_payments (provider, pp.id) with order_id, payment_id, amount, currency … FOR UPDATE   # 3.
    if rank(pp.status) <= rank(row.status) and row was not new: return ('ignored', 'older or same state')

    if pp.status == 'captured':
        accepted = SELECT 1 FROM provider_payments WHERE order_id = order.id AND is_accepted
        if order.status == 'pending_payment' and not accepted:
            # First verified capture for a payable order wins — whichever attempt it came from.
            UPDATE payments SET status = 'superseded' WHERE order_id = order.id AND id <> attempt.id
                   AND status IN ('pending','authorized')                      # frees the one-active index
            UPDATE payments SET status = 'succeeded' WHERE id = attempt.id      # allowed from pending/authorized/failed/expired
            UPDATE provider_payments SET status = 'captured', is_accepted = true WHERE id = row.id
            transition_order(order, 'pending_payment' -> 'processing')
            return ('applied', 'accepted capture')
        # Surplus capture: a second capture, a late capture of an old attempt, or the order is cancelled/expired/paid.
        UPDATE provider_payments SET status = 'captured', is_accepted = false WHERE id = row.id
        INSERT INTO refunds (order_id, kind, provider_payment_id, amount_minor, currency, status, reason,
                             request_key, receipt, origin)
               VALUES (order.id, 'provider', row.id, pp.amount, pp.currency, 'required', 'surplus capture',
                       'auto-surplus:' || pp.id, receipt_for('auto-surplus:' || pp.id), 'application')
               ON CONFLICT (request_key) DO NOTHING
        enqueue staff alert (outbox)                                           # the order is NEVER revived
        return ('applied', 'surplus capture → refund required')
    if pp.status == 'authorized': mark row 'authorized'; attempt pending → authorized; return ('applied', …)
    if pp.status == 'failed':     mark row 'failed'; if the attempt has no other live provider payment: attempt → 'failed'
                                  (order stays pending_payment; the customer can retry with a new attempt); return ('applied', …)
```
- The database index `provider_payments_one_accepted_per_order` is the final guard: even with a code defect, a second
  accepted capture for one order cannot be committed.
- Customer-visible: accepted capture → "Payment confirmed"; surplus capture → "We received an extra payment of ₹X for order
  N. It will be refunded to the original payment method; we'll confirm when it's processed." (The refund itself is only
  described as completed when its row is `completed`.)
- `payments.status` transitions added by this design: `failed|expired → succeeded` **only** inside
  `settle_provider_payment` with a verified capture; `pending|authorized → superseded`; `authorized → expired`.

### 7.6 Reconciliation (mandatory) and unpaid-order expiry
Runs from the background worker recommended in `docs/scheduler-architecture.md` (one advisory-lock-guarded run at a time per
store database; recorded in `job_runs`); every run is idempotent and uses the same row locks as the webhook path.
- **Reconcile** every 10 minutes: local attempts `pending`/`authorized` older than 5 minutes, and any order with
  `needs_review`: list the provider order's payments [CONFIRMED: `GET /v1/orders/{id}/payments` returns all authorised and
  failed payments for an order] and call `settle_provider_payment` for each. Also fetch refunds `pending` and refunds
  without `provider_refund_id` (§7.7).
- **Inconsistent states:** provider captured but local not → settle (normal case). Local `succeeded` but provider not
  captured → set `needs_review`, alert, hold fulfilment; never change money records automatically. A refund found in Razorpay
  that we did not create (dashboard refund) → insert a refunds row with `origin='external'` and the provider status.
  Amount mismatch → `needs_review`, never accepted.
- **Expire** unpaid orders after `UNPAID_ORDER_TTL_MINUTES` (60): per order, lock it; if still `pending_payment` and no
  attempt is `authorized`/`succeeded`, cancel it, cancel its pending attempt, restock. A capture arriving later is a
  surplus capture (§7.5).

### 7.7 Refund creation and idempotency (F4, F6)
Creation — one transaction, the captured payment row locked so concurrent requests cannot exceed the balance:
```
def request_refund(conn, provider_payment_id, amount, request_key, reason, actor):
    BEGIN
    pp = SELECT * FROM provider_payments WHERE id = provider_payment_id FOR UPDATE
    if pp.status != 'captured': raise NotRefundable            # [CONFIRMED] only captured payments can be refunded
    prior = SELECT * FROM refunds WHERE request_key = request_key
    if prior: COMMIT; return prior                             # replay of the same request → same row
    committed = SELECT COALESCE(SUM(amount_minor), 0) FROM refunds
                WHERE provider_payment_id = pp.id AND status IN ('required','requested','approved','pending','completed')
    if committed + amount > pp.amount_minor: raise RefundExceedsCaptured
    INSERT INTO refunds (…, kind='provider', status='approved' (staff) or 'requested', request_key, receipt=receipt_for(request_key))
    COMMIT
```
- A second concurrent request waits on the `FOR UPDATE` lock, then sees the first row in its sum — the captured amount can
  never be exceeded. Razorpay also rejects an amount greater than captured [CONFIRMED], as a second line of defence.
- **Sandbox refunds** (`kind='sandbox'`, development only) lock the `payments` row instead and check against its
  `amount_cents`; they never call Razorpay. Production refuses `kind='sandbox'`.

Sending to Razorpay (outside that transaction, by the worker):
1. `approved → pending` (short transaction), then `POST /v1/payments/{id}/refund` with `amount`, `receipt`, `notes`.
2. `receipt_for(request_key)` is deterministic (e.g. `rf_` + first 30 hex chars of SHA-256 of `store|request_key`), so every
   retry of the same request sends the **same receipt**. [CONFIRMED] Razorpay rejects a reused receipt for the same payment
   ("Duplicate receipt found for this refund request") — that is our duplicate-request protection. The refund `receipt`
   length limit is **[ASSUMPTION — verify; the 40-character limit is confirmed for orders]**. We do **not** rely on an
   `X-Refund-Idempotency` header (seen only on a Razorpay docs mirror; unconfirmed).
3. Response → store `provider_refund_id`; map status [CONFIRMED values]: `pending → pending`, `processed → completed`,
   `failed → failed`.
4. Timeout / network error → leave `pending` without `provider_refund_id`; reconciliation lists the payment's refunds
   (`GET /v1/payments/{id}/refunds` [CONFIRMED endpoint exists]) and attaches the one with our receipt. A retry that gets
   "Duplicate receipt" is treated as "already created" and resolved the same way. **Never** create a new receipt for the
   same `request_key`.
5. `failed` is terminal for that row; retrying is a new request with a new `request_key` (the failed amount is back in the
   refundable balance). [CONFIRMED] normal refunds fail for payments older than 6 months.

## 8. Test plan and credentials

All requirements above have scenarios in `docs/testing-plan.md` (payment safety, webhook safety, migration safety), run
against a **mocked Razorpay** HTTP server and the `*_test` databases. Manual end-to-end later in Razorpay **test mode**.
Needed from you: test key id and secret, webhook secret, alert email address, and approval for a public HTTPS tunnel to
receive webhooks on this Mac (Razorpay webhook URLs must use port 80 or 443 [CONFIRMED]); until then webhooks are tested with
locally signed requests.

## 9. Security requirements

- Secrets only in `.env` (600), hidden from `Settings` repr and logs; the frontend receives only the key id.
- Constant-time signature checks over the raw body; webhook endpoint size-limited and rate-limited; no order data in errors.
- Amounts/currency always from the database. Provider data is trusted only when it is either fetched server-side from
  Razorpay (callback, reconciliation) or carried in a webhook whose signature over the raw body verified; in both cases
  amount, currency, store and provider order id are checked against our own rows before anything changes.
- Store isolation: rows live in each store's own database; `notes.store` checked; a Store A event can never touch Store B.
- CSP for Razorpay Checkout added narrowly (docs/security.md); HTTPS for any non-local deployment.
- Logs: event id, type, outcome; never signatures, card/UPI/bank data (never received) or full payloads.

## 10. Razorpay facts: confirmed vs to verify

**Confirmed** (official documentation, read in Phase 1.2):

| Fact | Source |
|---|---|
| Webhook signature `X-Razorpay-Signature`, HMAC-SHA256 of the raw body with the webhook secret; do not parse before verifying | Validate and Test Webhooks |
| `x-razorpay-event-id` is unique per event; use it to detect duplicates; duplicates and out-of-order delivery are expected | Validate and Test Webhooks; Webhook Best Practices |
| Non-2xx or no response within 5 s = failure; retried with exponential backoff for 24 h; then the webhook is disabled and an alert email sent | Webhook Best Practices |
| Webhook URLs must use port 80 or 443; separate Test-mode and Live-mode webhook URLs | Webhooks |
| Automatic capture is default; window 12 minutes – 3 days; order-level values override the dashboard; uncaptured authorised payments are auto-refunded (normal speed, ~5–7 working days); a Capture API exists | Capture Settings |
| Order amount in the smallest sub-unit; `receipt` ≤ 40 chars; `notes` ≤ 15 pairs | Python Integration Steps |
| Payment signature: HMAC-SHA256(key_secret, `order_id|payment_id`), using the server-stored order id | Python Integration Steps |
| One order can have several payment attempts; `GET /v1/orders/{id}/payments` lists authorised and failed payments | Fetch Payments for an Order |
| Refund statuses `pending`, `processed` (final), `failed`; partial refunds; only captured payments refundable; amount > captured rejected; normal refunds fail after 6 months; reused refund `receipt` is rejected as a duplicate; `GET /v1/payments/{id}/refunds` exists | Refunds API; Create a Normal Refund |
| Test and live keys are separate; test mode is a simulation | Authentication |

**To verify before implementation** (not confirmed on the pages read):
1. API key prefixes (`rzp_test_` / `rzp_live_`).
2. Exact order fields for capture options and the Capture API request.
3. The status Razorpay reports for an authorisation auto-refunded after the window (mapping to our `expired`).
4. Refund `receipt` maximum length.
5. `X-Refund-Idempotency` header (seen only on a docs mirror) — not used by this design.
6. Full list and payloads of refund webhook events (`refund.*`) and of `payment.authorized` / `payment.captured` / `payment.failed` / `order.paid`.
7. Exact retry count/intervals within the 24-hour window.
8. Merchant KYC and website/policy requirements before test → live.

Sources: https://razorpay.com/docs/webhooks/validate-test/ · https://razorpay.com/docs/webhooks/best-practices/ ·
https://razorpay.com/docs/webhooks/ · https://razorpay.com/docs/payments/payments/capture-settings/ ·
https://razorpay.com/docs/payments/server-integration/python/integration-steps/ · https://razorpay.com/docs/api/orders/fetch-payments/ ·
https://razorpay.com/docs/api/refunds/ · https://razorpay.com/docs/api/refunds/create-normal/ · https://razorpay.com/docs/api/authentication/

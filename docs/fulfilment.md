# Order fulfilment (Phase F)

Staff (accounts with role `agent`, one per store database) fulfil orders at **`/staff/orders`** on their own storefront.

## What staff can do

| Order status | Actions offered | Becomes |
|---|---|---|
| `processing` (paid) | **Mark as shipped** — carrier and tracking number required; tracking link (`https://` only), estimated delivery and a staff note optional | `shipped` |
| `shipped` | Mark out for delivery · Mark as delivered · Record a return (reason required) | `out_for_delivery` / `delivered` / `returned` |
| `out_for_delivery` | Mark as delivered | `delivered` |
| `delivered` | Record a return (reason required) | `returned` |
| `shipped`, `out_for_delivery` | Correct the carrier / tracking (`PUT …/tracking`), recorded in history | (unchanged) |
| `pending_payment`, `cancelled`, `returned` | none | — |

Not available, on purpose: cancelling a **paid** order (needs a refund; payments are sandbox-only and out of scope),
editing items, prices, customers or payments, and restocking returned goods (a business decision: is it resaleable?).
This is not an admin console.

## Guarantees (enforced by the server, `backend/app/fulfilment.py`, `routers/staff.py`)

* **Authorisation:** every `/api/stores/{store}/staff/*` endpoint requires a signed-in agent whose token was issued by
  *that* store (Store A staff get 403 on Store B, customers get 403, anonymous 401).
* **Valid transitions only:** the order state machine (`order_state.ORDER_TRANSITIONS`) refuses anything else (409
  `invalid_transition`).
* **No double actions from stale screens:** each request carries the status the staff member was looking at
  (`expected_status`); if the order has changed, 409 `stale_status` and nothing happens. The order row is locked for the
  whole change.
* **History with actors:** every status change — order placed (customer), payment confirmed (system), customer
  cancellation, every staff action and tracking correction — writes an `order_status_history` row in the same
  transaction, naming the account. Orders that existed before migration 0005 have no earlier history (nothing is guessed).
* **Customers see** the status timeline, carrier, tracking number and link on their order page — **not** staff notes or
  which staff account acted. Customer endpoints accept no fulfilment fields (unknown fields are rejected).
* **Input rules:** carrier 2–40 letters/digits/`& . -`; tracking number 4–40 letters/digits/`-` (stored upper-case);
  tracking link `https://…`, ≤ 300 characters, no spaces or quotes; notes ≤ 500 characters (React renders them as text).

## Database change

Migration `0005_fulfilment.sql` (additive): `orders.tracking_url`, `orders.shipped_at`, `orders.delivered_at`, table
`order_status_history`. Down script `down/0005_fulfilment.down.sql` refuses while any history or tracking data exists
unless `avc.allow_data_loss` is set after a verified backup. **Applied to the `*_test` databases only**; the development
databases need your authorisation (see `docs/database-safety.md`).

## Open business decisions

Carriers to use and their tracking-URL formats (a template per carrier could fill the link automatically), whether
returned goods go back into stock, and how refunds for returns are handled once a real payment provider exists
(`docs/business-information.md`, B9–B10, B20).

# Customer care: what Scout and Maple can do

Scout (Summit Trail Co.) and Maple (Bloom & Brew) answer customer-care questions in **Tamil, English and Hindi**,
typed or spoken, using the same assistant pipeline as before (`backend/app/assistant/`):

```
message ─▶ language identification (language.py, unchanged)
        ─▶ intents + references (intent.py: shopping intents + customer-care intents, typos/quotes normalised)
        ─▶ verified data through the existing repository/commerce functions (care.py + service.py)
        ─▶ deterministic reply from reviewed templates (i18n.py + care_text.py)  ──▶  proposed actions (buttons)
        ─▶ local LLM phrasing ONLY for English store-policy, greeting and contact answers, grounding-checked (Phase 1)
        ─▶ final check: products/add-to-cart rebuilt from this store's catalogue; placeholders blocked
```

Customer-specific answers (orders, payments, refunds, cancellations, carts), proposed actions, escalations and
every Tamil/Hindi reply are **deterministic**: the model is never called for them.

## Capabilities

**Verified** = answered from the database for the signed-in customer (or the store's own data).
**Guided** = steps and the store's support contact; the system cannot do it itself.

| Area | What happens | Kind |
|---|---|---|
| Order status, tracking, ETA, history | Own orders only; carrier + tracking + expected date | Verified |
| Late / missing delivery | On track vs past the expected date, tracking, then the support e-mail | Verified + guided |
| "Delivered but not received" | Delivery date on record, what to check, support e-mail; no investigation can be opened from chat | Verified + guided |
| Cancel an order | **Unpaid** orders: a *Cancel order* button → second confirmation → existing `POST /orders/{n}/cancel`. Paid / shipped orders: why not, and the next step. Several unpaid orders: asks which | Verified action |
| Change items or address | Not supported by the system; unpaid → cancel and re-order; paid → support | Guided |
| Payment status / failure | Latest payment record per order (declined, pending, confirmed with amount), link to the payment page, sandbox notice | Verified |
| "Paid but nothing happened", double charge | What the records show; the one-successful-payment-per-order rule; real double charges → support (no reversals from chat) | Verified + guided |
| Refund status | Returned orders are described only as *returned*: there are no refund records, so the assistant says it can't confirm whether, how much or when a refund was issued (truth.py `REFUND_STATES`); paid-then-cancelled orders go to support; never an invented refund | Verified |
| Returns, exchanges | Store's own policy text; delivery date + return window (days parsed from the store policy); returns/exchanges are started by e-mail | Verified + guided |
| Damaged, defective, wrong or missing items | Steps, the minimum details to send (order number, description, photos), warranty/returns policy; no claim is registered from chat | Guided |
| Product search, stock, budget | As before, plus in-stock alternatives when an item is sold out | Verified |
| Compare products | Name, price, stock (and description in English), price difference | Verified |
| "Something cheaper / similar" | Same kind of product from the catalogue, using the product discussed earlier in the conversation | Verified |
| Add to cart | An *Add N × product* button (stock and the 10-per-item limit pre-checked); the existing cart API adds it; the chat confirms only after the API succeeds | Verified action |
| Reorder | Items of the last order, with add buttons for those in stock | Verified action |
| Account help | Sign-in, registration, password reset (links); account edits and deletion are not available online → support | Guided |
| Checkout help | Steps, no guest checkout (cart is kept), Store A does not ship to AK/HI, validation messages explained, cart problems | Verified + guided |
| Discount codes, promotions | None are configured; free-shipping threshold from store data | Verified |
| Invoices | Not available; order totals from the order record | Verified + guided |
| Privacy, languages, accessibility | Short factual answers about how this app works | Guided |
| Website problems | Troubleshooting steps, then support | Guided |
| Bulk / business orders | Support contact; online limit of 10 per item | Guided |
| Product care and usage | Small set of general tips per store, labelled "General tip (not from the product listing)" | General advice |
| Frustration, "talk to a human" | Acknowledges, says honestly that no live agent or ticket exists, gives the store's e-mail and hours, and a summary of the customer's own words to paste | Guided |
| Same generic answer twice | Escalates to the support contact instead of repeating | — |
| Unrelated questions | Short redirect to what the assistant can help with | — |

## Actions

The chat response now includes `actions` (see `ChatResponse.actions`):

| Type | What the widget does |
|---|---|
| `link` | Navigates inside the store (`/cart`, `/checkout`, `/account`, `/register`, `/forgot-password`, `/orders/{n}/pay`), or opens an e-mail to the store (`mailto:`) |
| `add_to_cart` | On tap, calls the existing `POST /cart/items`; says "Added …" only if the returned cart contains the item, otherwise shows the server's reason |
| `cancel_order` | First tap asks "Cancel this order? This can't be undone." with *Yes* / *No*; *Yes* calls the existing cancel endpoint and says "cancelled" only if the returned order status is `cancelled` |

The server validates every action again (store, session, ownership, order state, stock, limits). The assistant
itself never changes data.

## Privacy and safety rules

- Private data only for the signed-in customer of **this** store; other customers' and other stores' orders get the
  same "couldn't find order …" answer as unknown numbers.
- Never asks for card numbers, CVVs, passwords or one-time codes. If a customer types one, the reply warns them, the
  text is not used, and messages containing it are never sent to the model (also not as history).
- Never claims a refund, cancellation, complaint, ticket, callback or e-mail that the system did not confirm.
- Conversation references ("when will **it** arrive?") are taken from the same chat only, and re-checked against the
  database; a new question without such a reference is not tied to an older order.

## Customer-care requests (complaints, returns, simulated refunds, human help)

Recorded requests with a reference (`SA-CMP-00001`, `BB-RET-00002`, `…-RFD-…`, `…-ESC-…`), handled by staff in
**Staff → Customer care** (`/staff/care`) and followed by the customer under **My requests** (`/support/requests`).
Code: `backend/app/care_requests.py` (all rules), `routers/care.py` (API), `assistant/care_flow.py` (conversation),
`pages/CarePages.jsx`, `pages/StaffCarePages.jsx`; migration `0009_care_requests`.

| Request | Who can request | Lifecycle (staff only, validated by the server) |
|---|---|---|
| Complaint | Any signed-in customer; order and item optional | open → under_review ⇄ awaiting_customer → resolved; rejected / closed need a reason |
| Return | Delivered orders within the store's own policy window (60 days Summit Trail, 30 days Bloom & Brew, parsed from the returns policy) | requested → under_review → approved / rejected → received → inspected → completed |
| Refund (**simulated**) | Orders with a recorded successful sandbox payment | requested → under_review → approved / rejected → simulated_completed. No payment provider is called and no money moves |
| Human help | Any signed-in customer; order optional | open → assigned → in_progress ⇄ awaiting_customer → resolved / closed. Recorded for staff review — never presented as a live agent |

- Customers can reply (a reply moves "waiting for your reply" back to staff) and withdraw a request only before staff start on it.
- One open request per kind per order item; double submissions are absorbed with an Idempotency-Key.
- Staff can assign (this store's staff only), add internal notes (never shown to customers), message the customer,
  and change the status; every change is in the request history; status changes and messages queue an update e-mail
  (`email.care_update`, sent by `app.worker`; development: `.run/outbox/`).
- Submitting a return never changes the order; staff still record returns with the existing order actions.
- **In the chat**, Scout and Maple recognise these requests in Tamil, English and Hindi, ask for what's missing
  (order → item → reason → description), show a review and submit only after an explicit "yes" / ஆம் / हाँ or the
  Confirm button; the reply quotes the reference the database returned. "What is the status of my complaint?" is
  answered from the customer's own requests. Policy questions ("what is the return policy?") still get the policy.

## Not supported by the system (documented, not simulated)
Refund payouts (refunds are a simulated record only), return labels, exchanges, order or address edits after placing,
account edits or deletion, invoices, discount codes, live chat with a person or callbacks, real e-mail delivery,
real payments, real phone calls.

**Policy text vs. the app:** Summit Trail Co.'s returns policy says "Return shipping is free with the prepaid label
from your account", but the app has no return labels. The assistant quotes the policy and says that returns are
arranged by e-mail. Either the policy text or the app should be updated.

## Known limitations

- Intent detection is rule-based (English, Tamil, Hindi and common romanized phrases); unusual phrasing can fall back
  to a clarification or the "tell me more" answer (and, if repeated, to the support contact).
- Tamil and Hindi templates were written carefully but have not been reviewed by a native speaker.
- Care tips are general advice, not product-specific instructions.
- Spoken answers use the same text; long answers (e.g. policies) are read in full.
- The phone simulator uses the same answers in English but shows no buttons.

## Tests

`backend/tests/test_customer_care.py` (76 tests): intent phrasing in three languages, false-match guards, product
comparison, alternatives, cheaper follow-ups, care tips per store, add-to-cart proposals and limits, staff accounts,
sign-in requirements in three languages, ownership and cross-store isolation, follow-up references, cancellation with
confirmation, payment failure/success from real sandbox records, duplicate-charge escalation, refund honesty, return
windows per store, account and checkout help, unsupported capabilities, human requests, frustration, repeated
failures, off-topic redirects, secrets never forwarded to the model, care answers never using the model, Tamil/Hindi
action labels, voice-channel parity. Browser checks of the action buttons ran in headless Chrome on an isolated test
stack (not a physical microphone).

## Trust and correctness rules (Phase 1)

- **Refunds**: no refund records exist, so a `returned` order is never called refunded (any language). See `assistant/truth.py`.
- **Payments**: payment answers come from the configured provider's real capabilities (today: sandbox only — no cards, UPI,
  wallets, gift cards or COD), never from the stored payment policy text.
- **Policy text**: sentences promising services the system lacks (prepaid return labels, store credit) are dropped from answers
  and from the model's context; the stored text itself still needs a reviewed data correction, so it is logged at start-up and
  listed under `policy_warnings` in `/api/health`.
- **Products**: product, price and stock answers are built from catalogue rows only (the model is not used for them). Every
  product card and add-to-cart button is re-checked against this store's catalogue before sending.
- **Model replies** (English policy/greeting/contact only) are rejected if they contain placeholders, links or markdown, prices,
  numbers or rupee amounts not in the facts, catalogue products the answer didn't include, sign-in demands the draft didn't make,
  or more than a few words that appear nowhere in the facts or the question.
- **Budgets**: ₹ / Rs. / INR / rupees (also Tamil and Hindi forms) are recognised and applied directly to the INR
  demonstration prices. A budget in another currency (e.g. dollars) is explained and not applied — never converted with a
  guessed rate.
- **Tickets**: no ticket system exists; ticket requests get an honest answer and the store's support e-mail and hours.
- **Each assistant's voice**: catalogue answers open with Scout's or Maple's own introduction; Scout adds a safety note for
  harsh-conditions questions, Maple notes that caffeine/allergen/health data isn't in the listings.

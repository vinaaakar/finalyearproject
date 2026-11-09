# Customer care: what Scout and Maple can do

Scout (Summit Trail Co.) and Maple (Bloom & Brew) answer customer-care questions in **Tamil, English and Hindi**,
typed or spoken, using the same assistant pipeline as before (`backend/app/assistant/`):

```
message ─▶ language identification (language.py, unchanged)
        ─▶ intents + references (intent.py: shopping intents + customer-care intents, typos/quotes normalised)
        ─▶ verified data through the existing repository/commerce functions (care.py + service.py)
        ─▶ deterministic reply from reviewed templates (i18n.py + care_text.py)  ──▶  proposed actions (buttons)
        ─▶ local LLM phrasing ONLY for plain English shopping answers, grounding-checked (unchanged rules)
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
| Refund status | Orders recorded as *returned and refunded*; paid-then-cancelled orders flagged for support; otherwise "no refund recorded" — never an invented refund | Verified |
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

## Not supported by the system (documented, not simulated)

Refund initiation or reversal, return labels and return requests, exchanges, order or address edits after placing,
account edits or deletion, invoices, discount codes, complaint or warranty tickets, live-agent handoff or callbacks,
real e-mail delivery, real payments, real phone calls.

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

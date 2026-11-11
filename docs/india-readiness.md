# India readiness (Phase I)

Status: **architecture in place, both stores still run the US market** (USD prices, US addresses), because switching
needs business decisions nobody but the owner can make. Nothing below invents a price, fee, delivery time, address or
tax detail. Related: `docs/india-razorpay-design.md` (earlier design; payments remain out of scope),
`docs/business-information.md` (owner decisions B1–B20).

## Implemented

| Area | What exists | Where |
|---|---|---|
| Market configuration | `STORE_A_MARKET` / `STORE_B_MARKET` = `US` (default) or `IN`; anything else is a configuration error | `backend/app/config.py`, `app/markets.py` |
| Indian addresses | 28 states + 8 union territories (ISO 3166-2:IN codes after the 2023 update: CG, OD, TG, UT — verify before launch), 6-digit PIN `^[1-9][0-9]{5}$`, Indian mobile number (spaces, hyphens, +91 accepted; stored as E.164 `+91XXXXXXXXXX`), optional landmark | `markets.validate_address`, tests `test_phaseI_markets.py` |
| Shipping zones | Zone resolution by longest PIN prefix, then state/UT; **no zones are configured**, so an `IN` store reports `shipping_configured: false` and the checkout form refuses review (“Delivery charges for this region haven’t been set by the store yet”) | `markets.shipping_zone`, `CheckoutPage.jsx` |
| Currency guard | The API **refuses to start** a store in the `IN` market while its catalogue currency is not INR (no conversion is ever applied) | `main.py` lifespan |
| INR formatting | `format_money(minor, currency)`: `₹1,24,999.00` (Indian grouping), USD unchanged (`$1,249.99`); both existing `money()` helpers now delegate to it | `markets.py` |
| One source of address rules | `GET /api/stores/{id}/market` (regions, labels, postal pattern, phone, landmark, currency); the checkout form is built from it, falling back to today’s US rules for an older API | `routers/catalog.py`, `CheckoutPage.jsx` |
| Storefront languages | Tamil / English / Hindi switch in the footer, remembered per store in the browser; translates the header, footer and the Help, Shipping, Returns and Contact pages; sets `<html lang>`; store policies are fetched in the chosen language (`?lang=ta|hi`) | `uiText.js`, `StoreApp.jsx`, `SupportPages.jsx`, `e2e/language.spec.cjs` |
| Mobile-first | All new pages pass the 375 / 390 / 768 / 1280 px layout checks, also in Tamil | `e2e/mobile.spec.cjs`, `e2e/language.spec.cjs` |
| Separate brands | Unchanged: each store keeps its own theme, palette, art and assistant persona | `apps/store-*/src/theme.css`, `art.jsx` |

## Not done yet (honest list)

1. **India checkout end to end.** The checkout API still accepts the US address schema only; India addresses are
   validated by `markets.validate_address` but orders don’t yet store phone/landmark (needs an additive migration, e.g.
   `orders.shipping_phone`, `shipping_landmark`, `currency`) and the quote does not price zones. Blocked mainly on the
   decisions below; the code path is designed (`docs/india-razorpay-design.md` §3, §5–6).
2. **Currency on every amount.** `money()` callers still pass no currency (USD default). Before an INR store goes live,
   every call must pass the store’s catalogue currency, and orders need a currency column.
3. **Interface translation coverage.** Translated: navigation, footer, support pages. Still English only: home,
   product, cart, checkout, payment, account, order and staff pages. The chat assistant itself is fully trilingual.
4. **Native-speaker review** of every Tamil and Hindi string in `uiText.js` (written for this project, unreviewed).
5. **Default interface language** is English (the assistant starts in Tamil). Making Tamil the storefront default is an
   owner decision.

## Decisions needed before a store can switch to `IN`

INR price for every product (B16) · shipping zones, fees, free-shipping thresholds and delivery times (B13–B15) ·
business identity: legal name, address, GSTIN, grievance officer, support phone and hours in IST (B1–B7) · return
and refund rules for India (B8–B11) · carriers (B20) · whether the interface defaults to Tamil.

## How to switch a store (after those decisions)

1. Back up; reprice the catalogue to the approved INR list and set `store_profile.currency = 'INR'` (a reviewed data
   migration, never a conversion).
2. Configure the shipping zones (owner data) and apply the order-columns migration through `python -m app.migrate`.
3. Set `STORE_B_MARKET=IN` (for example) and restart the API: it refuses to start if step 1 is missing.

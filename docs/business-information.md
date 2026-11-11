# Business information register (Phase A)

Everything a customer can read, or the assistants can say, about the two stores, and how far it can be trusted.
Both stores currently run on **synthetic demonstration data** (`backend/app/seed.py`): the company names, e-mail
addresses (reserved `example.com` domain), policies, products, prices, customers and orders are fictional. Nothing
below may be "filled in" by the software or by an AI: each **OWNER** item needs a decision from the business owner.

Status: **CORRECTED** = contradicted what the system does, fixed (code + migration 0004) · **SYSTEM** = derived from the
running system, true by construction · **DEMO** = invented demo value, must be confirmed or replaced by the owner ·
**MISSING** = not published anywhere; the assistants say so instead of guessing.

## 1. Claims that contradicted the system (corrected)

| Store | Claim (as seeded) | Why it was false | Fix |
|---|---|---|---|
| A + B | Payment policy: Visa, Mastercard, Amex, Discover, PayPal, Apple Pay, Google Pay, gift cards | Only a **sandbox** payment provider exists; no real payment method is accepted | Payment answers always come from the configured provider (`assistant/truth.py`, since Phase 1); stored text replaced with the sandbox statement (migration `0004_policy_truth`, seed) |
| A | “Return shipping is free with the prepaid label from your account” | No return-label feature exists | Sentence removed (EN/TA/HI) |
| B | “… returned within 30 days for a refund **or store credit**” | No store-credit feature exists | “or store credit” removed (EN/TA/HI); the 30-day rule is kept |
| A + B | Store information API (`GET /api/stores/{id}`) returned the **raw** policy text | Exposed the claims above to any page using it | Now returns `verified_policies` (same filter as the assistant), optionally in `?lang=ta|hi` |
| A + B | “What is your GST number?” → “please sign in to look up your order” | Mis-routed to private invoice handling | New *business_info* intent: states that address, phone and tax details are not published and gives the published support e-mail |

The pre-correction text is kept in `policies_backup_0004` when the migration runs, and `down/0004_policy_truth.down.sql`
restores it. **Migration 0004 has been applied only to the `*_test` databases**; applying it to the development databases
needs your authorisation (see `docs/database-safety.md` → migration procedure). Until then the running system still
filters the claims at read time, so customers don’t see them either way.

## 2. Facts the owner must confirm or supply

| # | Item | Store A today | Store B today | Status | Needed for |
|---|---|---|---|---|---|
| B1 | Legal business name / entity | “Summit Trail Co.” (demo brand) | “Bloom & Brew” (demo brand) | DEMO | Policies, invoices, Contact page, payment provider |
| B2 | Registered / business address | — | — | MISSING | Contact page, invoices, legal pages (India: required for e-commerce entities) |
| B3 | Support phone number | — | — | MISSING | Contact page |
| B4 | Support e-mail | `help@summittrail.example.com` | `care@bloomandbrew.example.com` | DEMO (reserved domain: cannot receive mail) | Contact page, assistant, notification e-mails |
| B5 | Support hours **and time zone** | Mon–Fri 8am–6pm **MT** | Every day 9am–8pm **ET** | DEMO (US time zones; India launch needs IST) | Contact page, assistant |
| B6 | GSTIN, PAN, other tax registration | — | — | MISSING | Invoices, legal pages |
| B7 | Grievance officer name and contact (India Consumer Protection (E-Commerce) Rules) | — | — | MISSING | Contact / legal page |
| B8 | Return window | 60 days, unused, original packaging | 30 days, unused kitchenware; opened food final sale | DEMO | Returns page, assistant |
| B9 | Who pays return shipping; how returns are started | not stated (the “prepaid label” was false) | not stated | MISSING | Returns page |
| B10 | Refund method and timing | “full refund to the original payment method” | “refund” | DEMO (no refunds can be processed: sandbox only) | Returns page |
| B11 | Damaged-item policy | via warranty | “Damaged items are replaced free of charge” | DEMO | Returns page |
| B12 | Warranty terms | 2 years on “Summit-brand” gear (no product is marked as Summit-brand) | 1 year on electric appliances | DEMO / ambiguous | Product pages, assistant |
| B13 | Shipping rates and free-shipping threshold | $6.95, free over $75, expedited $14.95 | $4.99, free over $50, no expedited | DEMO (USD) | Checkout, Shipping page |
| B14 | Delivery times and dispatch cut-off | 3–5 business days; same-day if before 1pm MT | 2–4 business days; coffee within 48 h of roasting | DEMO | Shipping page, assistant |
| B15 | Where you ship | contiguous US only (Alaska/Hawaii refused) | US | DEMO (India launch: zones by state/PIN) | Checkout |
| B16 | Prices and currency | USD | USD | DEMO — **INR prices are a business decision; no conversion will be applied** | Catalogue, checkout |
| B17 | Accepted payment methods | none (sandbox) | none (sandbox) | SYSTEM — payment-provider integration is out of scope | Payment page |
| B18 | Product facts (weights, ratings, materials) | seed descriptions | seed descriptions | DEMO | Product pages, assistant |
| B19 | Privacy policy, terms of sale | — | — | MISSING | Legal pages, sign-up |
| B20 | Carriers used and tracking URL formats | demo carriers UPS/USPS/FedEx on demo orders | demo carriers | DEMO | Fulfilment (Phase F), order pages |

## 3. How the system behaves while these are missing

* The assistants answer policy questions **only from the stored policy text after the truth filter**, and product
  questions only from the catalogue (Phase 1 grounding rules, `docs/security.md`).
* Address, phone, tax registration and legal entity: the assistants say the store hasn’t published them and give the
  support e-mail (tested in English, Tamil and Hindi, `backend/tests/test_phaseA_content_truth.py`).
* Refunds: the assistants never claim a refund was requested, approved or paid (`truth.REFUND_STATES`).
* The support pages added in Phase E show only stored, verified information and label missing items as not published.

## 4. Data and recovery review (Phase A item 7)

`docs/database-safety.md` was checked against the scripts it names (`backup_db.sh`, `dbsafety.py verify|restore-check|precheck`,
`backup_to_drive.sh`, `restart_api.sh`, `test.sh`): all exist with the documented arguments. Gaps carried into later phases:
the migration runner still lacks checksums, locking and an enforced precheck (Phase G, `docs/migration-runner-safety.md`),
and the Google Drive copy is unencrypted plain SQL, acceptable only for synthetic data (Phase J: encrypted offsite backups).

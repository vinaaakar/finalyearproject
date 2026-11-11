# Mobile responsiveness and accessibility testing

Testing layer for both storefronts: Store A (Summit Trail Co., assistant Scout) and Store B (Bloom & Brew,
assistant Maple). Phase C added the tests and found seven defects; **Phase D fixed all seven** (see "Phase D fixes").
Every former known-defect check is now an ordinary assertion, and no known defects or axe baseline entries remain.

## Isolation

All browser suites run against the isolated stack that `frontend/playwright.config.cjs` starts and stops itself:

| Piece | Where | Data |
|---|---|---|
| Test API | `scripts/e2e_api.py` on 127.0.0.1:**18000** | `store_a_test` / `store_b_test` only; refuses to start otherwise or if their migrations differ; never migrates, seeds or resets; model and speech engines off; rate limits raised for this process only |
| Store A | production build, `vite preview` on **15180** | proxies `/api` → 18000 |
| Store B | production build, `vite preview` on **15181** | proxies `/api` → 18000 |

The development stack (API 8000, storefronts 5180/5181, development databases) is never used. Each run creates
synthetic customers (`e2e-…@example.com`), carts, and orders that the tests cancel again; these rows accumulate in
the `*_test` databases until the backend suite next resets them. Browser: the installed Google Chrome
(`channel: 'chrome'`), headless; no Playwright browser download.

## Commands (from `frontend/`)

| Command | Runs |
|---|---|
| `npm test` | component tests (Vitest, Phase B) |
| `npm run test:e2e` | every browser suite below |
| `npm run test:e2e:journey` | the customer journey (Phase B) |
| `npm run test:e2e:mobile` | mobile/responsive suite |
| `npm run test:e2e:a11y` | axe accessibility suite + keyboard-only suite |
| `node e2e/mutations/run.cjs [id…]` | mutation checks (builds broken *copies*; see below) |

Each browser command builds both storefronts, starts the isolated stack, runs, and shuts it down.
Add `--project store-a` (or `store-b`) after `--` to run one store. Failure traces go to `frontend/test-results/`
(git-ignored).

## Coverage

### Mobile responsiveness — `e2e/mobile.spec.cjs` (58 tests)

Each store at **375×812, 390×844, 768×1024** (phone/tablet emulation with touch) and **1280×800** (desktop regression):

| Screen | Checks |
|---|---|
| Home + navigation | scroll padding is larger than the sticky header (K-1 regression); no page-level horizontal overflow, nothing outside the viewport, no overlapping controls; every nav item visible, inside the viewport and ≥ 24 px tall (WCAG 2.2 SC 2.5.8); Cart / Sign in / brand links navigate; footer not hidden by the chat launcher |
| Search + listing | search box fits; results; category chips toggle (`aria-pressed`); every “Add … to cart” button reachable (not under the launcher); the “added” toast fits the screen and doesn’t hide the launcher |
| Product detail | layout; Add to cart not obscured; image no wider than the screen; inline confirmation; cart count updates |
| Cart | layout; quantity select and Remove usable; Checkout button reachable and works |
| Checkout | both steps; every field editable, ≥ 44 px wide and ≥ 24 px tall, shows a realistic value in full (no scrolling inside the box), inside the viewport and not obscured; Review / Place order / Edit shipping reachable |
| Payment | layout; Pay and Cancel reachable; cancel confirmation fits and its buttons are reachable; cancellation completes |
| Checkout width sweep | at 13 widths from 375 to 1280 px the ZIP field shows a full ZIP+4 and the City field “Colorado Springs” (M-1 regression) |
| Chat | launcher inside the viewport; dialog fits the screen; Tamil welcome renders (a font can draw Tamil) and isn’t clipped; close / input / send / language select inside the viewport; suggestions wrap inside the panel; switching language updates `lang`; English and Tamil messages render without clipping; closing restores the launcher |

“Overflow” means the *page* scrolls sideways or an element extends past the screen edge. Content inside an
intentionally scrollable box (`overflow-x: auto/scroll`) that itself fits is not counted; content cut off by
`overflow: hidden` is. On phones the check compares with the emulated screen width, because Chrome widens the
layout viewport (zooms out) when content overflows.

### Accessibility — `e2e/a11y.spec.cjs` (16 tests)

axe-core 4.10.2 via `@axe-core/playwright` with tags `wcag2a wcag2aa wcag21a wcag21aa wcag22a wcag22aa`, on each
store at **desktop light, phone (390 px) light, and desktop dark** (both stores have a dark palette):
home, product listing (search results), product detail, cart, checkout shipping step, checkout review step,
payment, payment cancel confirmation, chat (Tamil welcome) and chat (English conversation with product cards).
That is 30 scans per store; 33 distinct axe rules were evaluated and passed somewhere (names, ARIA validity, labels,
contrast, `lang`, target size, bypass blocks, etc.).

Extra checks axe does not make under WCAG tags: exactly one `h1` in `<main>`, no skipped heading levels, every
`<img>` has `alt`. And a **supplementary contrast check** for elements axe marks “incomplete” (text on the hero
gradients, the cart badge, the launcher label, chat header and footer text): the worst-case ratio is computed
against every gradient stop, including the text’s opacity, in light and dark themes.

### Keyboard only — `e2e/keyboard.spec.cjs` (18 tests)

| Test | Verifies |
|---|---|
| Tab / Shift+Tab | skip link first and visible on focus; header order (skip, brand, Shop, Sign in, Cart, Help) and exact reverse order; skip link moves focus into `<main>`; walking every stop on the home page: no invisible stops, every stop shows a focus indicator, focus wraps (no trap), the chat launcher is reachable |
| Enter / Space | Space toggles a category chip; Enter submits search; Space on a card’s Add button; Enter follows a product link; Enter on Add to cart |
| Chat without a mouse | open with Enter; focus moves into the input; send with Enter; reach the language select and change it (type-to-select); every chat control shows focus; **Escape closes it and focus returns to the launcher**; reopening keeps the conversation; the close button returns focus to the launcher; opened from the header’s Help button, Escape returns focus to Help; Escape with the chat closed changes nothing |
| Checkout without a mouse | cart → Checkout → every field in order (type-to-select for State) → Enter submits → Place order → payment → Cancel → **focus moves into the confirmation**; “Keep my order” **returns focus to “Cancel this order”**; reopen → Tab → Space confirms |
| Backwards focus (390 px and 1280 px) | Shift+Tab from the bottom of the checkout review: no focused control is completely hidden, including by the sticky header (WCAG 2.2 SC 2.4.11) |
| Phone chat is modal (390 px) | `aria-modal="true"`; every background region is `inert`; Tab and Shift+Tab never leave the chat; background links can’t take focus; Escape closes it, focus returns to the launcher, the background is interactive again |
| Resizing with the chat open | phone → desktop width makes it non-modal (nothing inert); back to phone makes it modal again |
| Desktop chat (1280 px) | stays a non-modal floating panel: `aria-modal="false"`, nothing inert, the page stays usable beside it |

## Findings (Phase C) — all fixed in Phase D

These were found by the Phase C run (light theme: 0 axe violations). The table records them as found; the fix and the
evidence after the fix are in “Phase D fixes”. Today **all axe scans, light and dark, report 0 violations**.

| ID | Severity | Store | Finding | Affected element / selector | WCAG | Recommended remediation |
|---|---|---|---|---|---|---|
| **A-1** | Serious | A (dark theme only) | White text on the dark-theme accent `#ea580c` is **3.55:1** (needs 4.5:1) | every `.btn-primary` (incl. `.card-add` “Add … to cart”, `a[href$="#catalog-heading"]` “Shop the collection”, Checkout, Review, Place order, Pay), `.launcher-label` “Ask Scout”, `.bubble-user` chat bubbles, `.cart-count` badge | 1.4.3 Contrast (Minimum), AA | In `apps/store-a/src/theme.css` dark block, change `--accent: #ea580c` to a darker orange, e.g. `#c2410c` (5.18:1, same as the light theme) |
| **K-4** | Serious | both | On phones (≤ 720 px) the chat covers the whole screen but is `aria-modal="false"` with no focus containment: Tab moves to the skip link, brand, Shop, Sign in… which are hidden behind it | `section.chat-panel[role=dialog]` | 2.4.3 Focus Order; 2.4.11 Focus Not Obscured (AA) | When the panel is full-screen, make it modal: `aria-modal="true"` and contain focus (e.g. set `inert` on the rest of the page while open) |
| **K-1** | Moderate | both (desktop: A on this page) | With the sticky header, moving focus *upward* (Shift+Tab) can scroll the focused control completely under the header | `.site-header` (sticky) covering e.g. “Place order · $…”, `.back-link` “← Back to cart” on checkout review | 2.4.11 Focus Not Obscured (Minimum), AA | `html { scroll-padding-top: <header height + margin>; }` (header is ~68 px on desktop and taller when it wraps on phones), or a non-sticky header on small screens |
| **K-5** | Moderate | both | Activating “Cancel this order” replaces the button with the confirmation, so keyboard focus falls to `<body>` | payment page `div[role=group][aria-label^="Confirm cancelling order"]` | 2.4.3 Focus Order | On open, move focus into the confirmation (its first button or a focusable heading); on “Keep my order”, return focus to “Cancel this order” |
| **K-3** | Moderate | both | Closing the chat leaves focus on `<body>` instead of the launcher | `.chat-launcher` | 2.4.3 Focus Order | Keep a ref to the launcher and focus it after `onClose` |
| **K-2** | Moderate | both | Escape does not close the chat dialog | `section.chat-panel[role=dialog]` | Not a WCAG failure for a non-modal dialog; expected by the ARIA dialog pattern | Handle `Escape` on the panel → `onClose()` (then K-3’s focus return) |
| **M-1** | Minor | both | At 768 px the checkout ZIP field shows 84 px of text but a valid ZIP+4 (“80302-1234”) needs ~113–116 px, so part of the value is scrolled out of view | `#ship-zip` in `.form-row` (grid `2fr 1fr 1.2fr`) | — (usability) | Give the ZIP column more room at > 720 px, e.g. `grid-template-columns: 1.6fr 1fr 1.4fr`, or `min-width: 11ch` plus padding |

Checked and **not** defects: text over both hero gradients (light and dark), Store B dark theme, the cart badge and
launcher in light themes, chat header/footer text, Tamil glyph rendering, heading hierarchy and image alternatives on
every scanned screen, target sizes, no keyboard traps, focus indicators on every stop.

## Phase D fixes

| ID | Fix | Files | Before → after |
|---|---|---|---|
| A-1 | Store A dark-theme `--accent` `#ea580c` → `#c2410c` | `apps/store-a/src/theme.css` | white text 3.55:1 → **5.18:1**; axe dark scans 21 violations → 0 |
| K-1 | `html { scroll-padding-top: 6rem }`; `8.5rem` at ≤ 720 px, where the header wraps to two rows | `packages/shared/src/styles.css` | focused “Place order” / “← Back to cart” fully hidden under the header → never hidden; header 68 px vs padding 96 px (desktop, tablet), 112 px vs 136 px (phones) |
| K-2 | `Escape` on the chat panel closes it (ignored while an input method is composing, so Tamil/Hindi IMEs keep using Escape) | `packages/shared/src/ChatWidget.jsx` | dialog stayed open → closes |
| K-3 | closing by the close button or Escape returns focus to the control that opened the chat (Help, “Ask … about this”), else to the launcher; closing through a navigation link (View cart, Sign in) doesn’t move focus | `ChatWidget.jsx` | focus on `<body>` → on the launcher / opener |
| K-4 | while the panel is full-screen (`max-width: 720px`, followed live via `matchMedia`): `aria-modal="true"` and every other region of the page is `inert` (no focus, no clicks, hidden from assistive technology); restored on close or when the screen widens. Desktop stays non-modal | `ChatWidget.jsx` | Tab reached the skip link, brand, Shop, Sign in… behind the chat → focus never leaves the chat |
| K-5 | the confirmation (`role=group`, now `tabIndex=-1`) receives focus when opened; “Keep my order” returns focus to “Cancel this order” | `packages/shared/src/pages/PaymentPage.jsx` | focus on `<body>` → in the confirmation, then back on the trigger |
| M-1 | the checkout form is a size container; when it is narrower than 540 px (tablets, where it sits beside the summary) the address row uses the existing phone layout (City full width, State + ZIP below). Wider forms keep the three columns | `styles.css` | ZIP showed 84 px of a 113–116 px ZIP+4 at 768 px → fits at all 13 widths tested (375–1280 px) |

No behaviour other than focus, Escape and layout changed: no checkout, payment, chat or language logic was touched.

## How known defects are tracked

* **axe:** `frontend/e2e/a11y-baseline.json` lists reviewed violations, matched by rule + store + view + theme +
  target pattern + message pattern. It is **empty** since Phase D. Any violation fails the suite; a baseline entry
  that stops occurring on a view it lists also fails, so fixed issues must be removed from the list.
* **Mobile and keyboard:** `KNOWN_DEFECTS` in `frontend/e2e/support/helpers.cjs` (**empty** since Phase D). A test
  that hits a listed defect asserts it is present and records it as an annotation; when the defect is fixed the
  test fails with “no longer reproduces”, so the entry is removed and the check becomes a normal assertion (this is
  how the seven Phase C findings were converted).

## Mutation checks

`node e2e/mutations/run.cjs` copies `packages/shared` and `apps/store-a` to `frontend/.mutation-tmp/`
(git-ignored), applies one defect to the copy, builds it into the copy’s own folder, serves that build on the
isolated port 15180 (`AVC_E2E_DIST_STORE_A`), runs the relevant tests for Store A, and deletes the copy.
The live source files are never modified.

| Mutation | Defect introduced (in the copy) | Detected by |
|---|---|---|
| `wide-element` | product grid columns 420 px wide on phones | mobile: layout problems on home (375 px) |
| `missing-label` | cart quantity `<select>` loses its label | axe `select-name` on cart |
| `missing-name` | icon-only chat close button loses its accessible name | axe `button-name` on chat |
| `not-keyboard` | chat launcher becomes a clickable `<div>` | keyboard: launcher not among Tab stops; chat cannot be opened by keyboard |
| `dialog-focus` | opening the chat no longer moves focus into it | keyboard: chat input not focused (desktop and phone tests) |
| `no-focus-ring` | global `:focus-visible` outline removed | keyboard: “every focused control shows a focus indicator” |
| `low-contrast` | light-theme accent lightened to `#fb923c` | axe `color-contrast` on product detail |
| `revert-A-1` | Store A dark accent back to `#ea580c` | axe dark scan + supplementary contrast check |
| `revert-K-1` | scroll padding removed | keyboard: backwards focus hidden under the header |
| `revert-K-2` | chat Escape handler removed | keyboard: chat still open after Escape |
| `revert-K-3` | focus restoration removed | keyboard: launcher not focused after closing |
| `revert-K-4` | background no longer made inert | keyboard: background not inert / focus escapes |
| `revert-K-5` | focus not moved into the cancel confirmation | keyboard: confirmation not focused |
| `revert-M-1` | narrow-form address layout removed | mobile: ZIP+4 doesn’t fit at 768 px; width sweep |

All fourteen are detected. The component tests also cover the Phase D behaviour (Escape, Escape during IME
composition, focus return to the launcher and to the opener, modal/inert on a full-screen match, confirmation
focus), and each of those was checked by removing the fix in a temporary copy. Two weaknesses found this way were fixed **in the tests**: the overflow check had treated
`overflow: hidden` ancestors as intentional scrolling and used the widened phone layout viewport (it missed
`wide-element`), and the first `missing-name` mutation was not a real defect (“✕” is itself an accessible name).

## Limitations

* Automated tools find only part of the accessibility problems. Not covered: screen-reader output and announcement
  quality (VoiceOver/TalkBack/NVDA), real speech input, zoom to 200/400 % and text-spacing overrides (SC 1.4.4,
  1.4.10, 1.4.12), forced-colours/high-contrast mode, reduced motion, and focus-indicator *contrast* (only presence is
  checked).
* One browser engine (Chrome). Mobile is emulated (viewport, touch, mobile meta viewport), not real iOS Safari or
  Android devices; the on-screen keyboard covering inputs cannot be tested this way.
* On macOS, arrow keys open a `<select>` list instead of changing the value, so tests use type-to-select.
* Voice controls are exercised only for presence and labels; speech engines are off in the isolated API.
* Pages that need special server states were not scanned: password reset, account order history, declined/approved
  payment results, out-of-stock products, error pages.
* Scans run with the live data in the `*_test` databases; contrast and layout of very long product names or
  translated (Hindi) UI text beyond the chat are not exercised.

* `inert` and container queries need current browsers (Chrome/Edge 105+, Safari 16+, Firefox 112+). In older
  browsers the chat still works but the background is not made inert, and the address row keeps three columns.

## Not completed

Nothing in the Phase C or Phase D scope was skipped.

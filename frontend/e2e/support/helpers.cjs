// Shared helpers for the browser test layers (mobile layout, accessibility, keyboard).
// All data setup goes through the ISOLATED test API (/api is proxied by `vite preview` to scripts/e2e_api.py on
// :18000, which uses the *_test databases only). Every customer is new and synthetic; every order is cancelled again.
const fs = require('node:fs');
const path = require('node:path');
const { expect } = require('@playwright/test');
const { default: AxeBuilder } = require('@axe-core/playwright');

const VIEWPORTS = [
  { name: 'small-mobile', width: 375, height: 812, isMobile: true },
  { name: 'mobile', width: 390, height: 844, isMobile: true },
  { name: 'tablet', width: 768, height: 1024, isMobile: true },
  { name: 'desktop', width: 1280, height: 800, isMobile: false },
];

const STORES = {
  'store-a': { name: 'Summit Trail Co.', assistant: 'Scout', product: 'daytrip-22l-daypack', productName: 'Daytrip 22L Daypack',
               search: 'backpack', address: { full_name: 'E2E Shopper', line1: '12 Kambam Main Road', city: 'Cumbum', region: 'TN',
                                              regionName: 'Tamil Nadu', postal_code: '625521', country: 'IN', phone: '98765 43210' } },
  'store-b': { name: 'Bloom & Brew', assistant: 'Maple', product: 'gooseneck-kettle', productName: 'Gooseneck Pour-Over Kettle',
               search: 'kettle', address: { full_name: 'E2E Shopper', line1: '45 MG Road', city: 'Bengaluru', region: 'KA',
                                            regionName: 'Karnataka', postal_code: '560001', country: 'IN', phone: '91234 56789' } },
};

// ---- data setup through the isolated API ------------------------------------------------------------------
async function api(request, storeId, method, p, { token, body, headers = {} } = {}) {
  const res = await request.fetch(`/api/stores/${storeId}${p}`, {
    method, data: body, headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...headers },
  });
  const text = await res.text();
  if (!res.ok()) throw new Error(`${method} ${p} → ${res.status()} ${text.slice(0, 200)}`);
  return text ? JSON.parse(text) : null;
}

async function createCustomer(request, storeId, label) {
  const email = `e2e-${label}-${storeId}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  const r = await api(request, storeId, 'POST', '/auth/register', { body: { email, full_name: 'E2E Shopper', password: 'E2e-Strong-Pass-42' } });
  return { token: r.access_token, customer: r.customer, expiresIn: r.expires_in };
}

async function setCartQuantity(request, storeId, auth, slug, quantity) {
  return api(request, storeId, 'PUT', `/cart/items/${slug}`, { token: auth.token, body: { quantity } });
}

async function placeOrder(request, storeId, auth) {
  await setCartQuantity(request, storeId, auth, STORES[storeId].product, 1);
  const { regionName, ...address } = STORES[storeId].address;   // eslint-disable-line no-unused-vars
  const quote = await api(request, storeId, 'POST', '/checkout/quote', { token: auth.token, body: { shipping_method: 'standard',
    destination: { country: 'IN', region: address.region, postal_code: address.postal_code } } });
  const r = await api(request, storeId, 'POST', '/checkout', {
    token: auth.token, headers: { 'Idempotency-Key': `e2e_${Date.now()}_${Math.floor(Math.random() * 1e9)}` },
    body: { shipping: address, expected_total_cents: quote.cart.total_cents },
  });
  return r.order.order_number;
}

async function cancelOrder(request, storeId, auth, number) {
  try { await api(request, storeId, 'POST', `/orders/${number}/cancel`, { token: auth.token }); } catch { /* already cancelled */ }
}

/** Pay an order in the SANDBOX (test mode only: no real money), through the same API the payment page uses. */
async function payOrder(request, storeId, auth, number) {
  const pay = await api(request, storeId, 'POST', `/orders/${number}/payments`, { token: auth.token });
  await api(request, storeId, 'POST', `/payments/sandbox/${pay.payment.reference}/complete`, { token: auth.token, body: { outcome: 'success' } });
  const r = await api(request, storeId, 'POST', `/orders/${number}/payments/verify`, { token: auth.token });
  if (r.order.status !== 'processing') throw new Error(`order ${number} not paid: ${r.order.status}`);
}

// Seeded staff accounts of the *_test databases (synthetic; see backend/app/seed.py). Never used against other databases.
const STAFF = { 'store-a': 'agent@summittrail.example.com', 'store-b': 'agent@bloomandbrew.example.com' };
async function staffLogin(request, storeId) {
  const r = await api(request, storeId, 'POST', '/auth/login', { body: { email: STAFF[storeId], password: process.env.AVC_E2E_AGENT_PASSWORD || 'AgentDemo!2026' } });
  return { token: r.access_token, customer: r.customer, expiresIn: r.expires_in };
}

/** India-only checkout: the form shows "Delivering to India" (no country choice); fill an Indian address. */
async function fillIndianAddress(page, a) {
  await expect(page.getByTestId('ship-country')).toHaveText('Delivering to India');
  await page.getByLabel('Address line 1').fill(a.line1);
  await page.getByLabel('City / Town').fill(a.city);
  await page.getByLabel('State / union territory').selectOption(a.region);
  await page.getByLabel('PIN code').fill(a.postal_code);
  await page.getByLabel('Mobile number').fill(a.phone);
}

/** Make the storefront start signed in as `auth` (the same sessionStorage record the app writes after login). */
async function signIn(page, storeId, auth) {
  const record = { token: auth.token, customer: auth.customer, expiresAt: Date.now() + auth.expiresIn * 1000 };
  await page.addInitScript(([key, value]) => { window.sessionStorage.setItem(key, value); },
    [`avc:${storeId}:session`, JSON.stringify(record)]);
}

// ---- layout checks (run inside the page) ------------------------------------------------------------------
/** Page-level horizontal overflow and elements outside the viewport. Excluded: visually-hidden elements (skip link,
 *  .sr-only text) and content inside an intentionally SCROLLABLE box (overflow-x auto/scroll) that itself fits.
 *  Content cut off by overflow:hidden is still reported (it cannot be reached at all).
 *  `deviceWidth` is the emulated screen width: on phones Chrome widens the layout viewport (zooms out) to fit
 *  overflowing content, so clientWidth alone would hide the problem. */
async function layoutProblems(page) {
  const deviceWidth = page.viewportSize().width;
  return page.evaluate((deviceWidth) => {
    const problems = [];
    const layoutWidth = document.documentElement.clientWidth;
    if (layoutWidth > deviceWidth + 1) problems.push(`layout viewport widened to ${layoutWidth}px on a ${deviceWidth}px screen (content forces the page to zoom out)`);
    const vw = Math.min(layoutWidth, deviceWidth);
    const docOverflow = document.documentElement.scrollWidth - vw;
    if (docOverflow > 1) problems.push(`page scrolls horizontally by ${docOverflow}px (scrollWidth ${document.documentElement.scrollWidth} > ${vw})`);
    const describe = (el) => {
      const id = el.id ? `#${el.id}` : '';
      const cls = typeof el.className === 'string' && el.className.trim() ? `.${el.className.trim().split(/\s+/).slice(0, 2).join('.')}` : '';
      return `${el.tagName.toLowerCase()}${id}${cls}`;
    };
    const visuallyHidden = (el) => {
      for (let n = el; n && n !== document.body; n = n.parentElement) {
        const s = getComputedStyle(n);
        if (s.display === 'none' || s.visibility === 'hidden') return true;
        if (n.classList.contains('sr-only') || n.classList.contains('skip-link')) return true;
        if (s.position === 'absolute' && (s.clip === 'rect(0px, 0px, 0px, 0px)' || s.clipPath === 'inset(50%)')) return true;
      }
      return false;
    };
    const inScroller = (el) => {
      for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) {
        const ox = getComputedStyle(n).overflowX;
        if (['auto', 'scroll'].includes(ox)) {
          const r = n.getBoundingClientRect();
          if (r.left >= -1 && r.right <= vw + 1) return true;   // contained by a box that itself fits
        }
      }
      return false;
    };
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height || visuallyHidden(el)) continue;
      if ((r.right > vw + 1 || r.left < -1) && !inScroller(el)) {
        problems.push(`${describe(el)} extends outside the viewport (left ${Math.round(r.left)}, right ${Math.round(r.right)}, viewport ${vw})`);
        if (problems.length > 12) break;
      }
    }
    return problems;
  }, deviceWidth);
}

/** Clipped text: elements that hide overflowing text (overflow hidden) without an intentional ellipsis. */
async function clippedText(page, scopeSelector) {
  return page.evaluate((scope) => {
    const root = scope ? document.querySelector(scope) : document.body;
    if (!root) return [`${scope} not found`];
    const out = [];
    for (const el of root.querySelectorAll('*')) {
      const s = getComputedStyle(el);
      if (!['hidden', 'clip'].includes(s.overflowX) || s.textOverflow === 'ellipsis') continue;
      if (!el.textContent.trim() || el.closest('.sr-only')) continue;
      if (el.scrollWidth > el.clientWidth + 1) out.push(`${el.tagName.toLowerCase()}.${el.className}: text clipped (${el.scrollWidth} > ${el.clientWidth})`);
    }
    return out;
  }, scopeSelector);
}

/** Interactive elements that overlap one another (fixed/floating elements excluded; they are checked separately). */
async function overlappingControls(page) {
  return page.evaluate(() => {
    const vis = (el) => { const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0'; };
    const floating = (el) => { for (let n = el; n; n = n.parentElement) { const p = getComputedStyle(n).position; if (p === 'fixed' || p === 'sticky') return true; } return false; };
    const els = [...document.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, [role=button]')]
      .filter((el) => vis(el) && !floating(el) && !el.closest('.sr-only, .skip-link'))
      .map((el) => ({ el, r: el.getBoundingClientRect() })).filter(({ r }) => r.width > 0 && r.height > 0);
    const out = [];
    for (let i = 0; i < els.length; i += 1) {
      for (let j = i + 1; j < els.length; j += 1) {
        const a = els[i], b = els[j];
        if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
        const w = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
        const h = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
        if (w > 2 && h > 2) out.push(`"${(a.el.textContent || a.el.getAttribute('aria-label') || a.el.tagName).trim().slice(0, 30)}" overlaps "${(b.el.textContent || b.el.getAttribute('aria-label') || b.el.tagName).trim().slice(0, 30)}" (${Math.round(w)}×${Math.round(h)}px)`);
      }
    }
    return out.slice(0, 10);
  });
}

/** Focus the control and report it if another element hides it completely (WCAG 2.2 SC 2.4.11 Focus Not Obscured).
 *  center: first scroll it to the middle of the screen, so only floating layers (chat launcher, toasts, dialogs) can
 *  cover it; without it the browser's own focus scrolling is tested (which a sticky header can defeat). Null = visible. */
async function obscuredWhenFocused(locator, { center = false } = {}) {
  if (center) await locator.evaluate((el) => el.scrollIntoView({ block: 'center', inline: 'nearest' }));
  await locator.focus({ preventScroll: center });
  return locator.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const pts = [[r.left + r.width / 2, r.top + r.height / 2], [r.left + 2, r.top + 2], [r.right - 2, r.top + 2], [r.left + 2, r.bottom - 2], [r.right - 2, r.bottom - 2]];
    const covers = pts.map(([x, y]) => document.elementFromPoint(x, y)).filter((hit) => hit && hit !== el && !el.contains(hit) && !hit.contains(el));
    if (covers.length === pts.length) {
      const c = covers[0];
      return `${el.tagName.toLowerCase()} "${(el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 40)}" is hidden by ${c.tagName.toLowerCase()}.${c.className}`;
    }
    return null;
  });
}

/** Rectangle of an element relative to the viewport, with an "inside" flag. */
async function insideViewport(locator) {
  const device = locator.page().viewportSize();
  return locator.evaluate((el, dev) => {
    const r = el.getBoundingClientRect();
    const innerWidth = Math.min(window.innerWidth, dev.width);
    const innerHeight = Math.min(window.innerHeight, dev.height);
    return { inside: r.left >= -1 && r.top >= -1 && r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1,
             insideX: r.left >= -1 && r.right <= innerWidth + 1,
             rect: { left: Math.round(r.left), top: Math.round(r.top), right: Math.round(r.right), bottom: Math.round(r.bottom) },
             viewport: { width: innerWidth, height: innerHeight } };
  }, device);
}

// ---- known defects -----------------------------------------------------------------------------------------
/** Confirmed application defects (docs/mobile-accessibility-testing.md, "Findings"). The application is NOT changed
 *  in this phase, so a test that hits one records it as an annotation instead of failing; if the defect stops
 *  reproducing (it was fixed), the test FAILS so the entry is removed and the check becomes a normal assertion. */
const KNOWN_DEFECTS = {
  // Empty: the Phase C findings (A-1, K-1…K-5, M-1) were fixed in Phase D and are now normal assertions.
};
function knownDefect(testInfo, id, present, details = '') {
  if (!KNOWN_DEFECTS[id]) throw new Error(`unknown defect id ${id}`);
  if (!present) throw new Error(`Known defect ${id} no longer reproduces (${KNOWN_DEFECTS[id]}). Remove it from KNOWN_DEFECTS and assert the fixed behaviour.`);
  testInfo.annotations.push({ type: `known-defect ${id}`, description: `${KNOWN_DEFECTS[id]}${details ? ` — ${details}` : ''}` });
}

// ---- accessibility (axe-core) -------------------------------------------------------------------------------
const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22a', 'wcag22aa'];
const BASELINE_FILE = path.join(__dirname, '..', 'a11y-baseline.json');
const loadBaseline = () => JSON.parse(fs.readFileSync(BASELINE_FILE, 'utf8')).known;

/** Baseline entries (reviewed, documented known violations) that apply to a store and view. */
function baselineFor(store, view, size) {
  return loadBaseline().filter((b) => b.stores.includes(store) && (b.views.includes('*') || b.views.includes(view))
    && (!size || !b.sizes || b.sizes.includes(size)));
}

/** Run axe and compare with the reviewed baseline of KNOWN violations (each documented in
 *  docs/mobile-accessibility-testing.md). Anything not in the baseline is returned as `unexpected`. */
async function axeScan(page, testInfo, { store, view, include, baselineView, size } = {}) {
  let builder = new AxeBuilder({ page }).withTags(AXE_TAGS);
  if (include) builder = builder.include(include);
  const results = await builder.analyze();
  const found = results.violations.flatMap((v) => v.nodes.map((n) => ({
    rule: v.id, impact: v.impact, help: v.help, tags: v.tags.filter((t) => /^wcag\d/.test(t)), target: n.target.join(' '),
    html: n.html.slice(0, 160), summary: (n.failureSummary || '').replace(/\s+/g, ' ').slice(0, 300),
  })));
  await testInfo.attach(`axe-${store}-${view}.json`, { body: JSON.stringify(found, null, 2), contentType: 'application/json' });
  if (process.env.AVC_A11Y_DISCOVER) {   // used to draft/review the baseline; never set in normal runs
    const incomplete = results.incomplete.flatMap((v) => v.nodes.map((nd) => ({ rule: v.id, impact: v.impact, target: nd.target.join(' '),
      summary: (nd.failureSummary || '').replace(/\s+/g, ' ').slice(0, 200) })));
    fs.appendFileSync(path.join(testInfo.project.outputDir, 'axe-discovery.jsonl'),
      `${JSON.stringify({ store, view, passes: results.passes.length, passedRules: results.passes.map((x) => x.id), found, incomplete })}\n`);
  }
  const candidates = baselineFor(store, baselineView || view, size);
  const matchOf = (f) => candidates.find((k) => k.rule === f.rule && new RegExp(k.target).test(f.target)
    && (!k.summary || new RegExp(k.summary).test(f.summary)));
  const known = found.filter((f) => matchOf(f));
  const unexpected = found.filter((f) => !matchOf(f));
  const matchedKeys = [...new Set(known.map((f) => matchOf(f).key))];
  return { found, known, unexpected, matchedKeys, passes: results.passes.length };
}

module.exports = {
  fillIndianAddress, VIEWPORTS, STORES, api, createCustomer, setCartQuantity, placeOrder, cancelOrder, signIn, payOrder, staffLogin,
  layoutProblems, clippedText, overlappingControls, obscuredWhenFocused, insideViewport, axeScan, expect,
  KNOWN_DEFECTS, knownDefect, baselineFor,
};

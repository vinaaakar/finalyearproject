// Automated accessibility scans (axe-core, WCAG 2.0/2.1/2.2 A + AA rules) of every main screen of each storefront
// (project), at desktop and phone widths, plus a heading-hierarchy check axe does not make under WCAG tags.
// Known violations live in e2e/a11y-baseline.json (each one reviewed and documented in
// docs/mobile-accessibility-testing.md). Any violation NOT in the baseline fails the test, and a baseline entry that no
// longer matches anything fails too, so the list cannot go stale.
const { test } = require('@playwright/test');
const h = require('./support/helpers.cjs');

const { expect } = h;
const SIZES = [{ name: 'desktop', width: 1280, height: 800 }, { name: 'mobile', width: 390, height: 844 },
  { name: 'desktop-dark', width: 1280, height: 800, colorScheme: 'dark' }];   // both themes have a dark palette
const matchedBaseline = new Map();   // "store|view" → Set of baseline keys that matched (per worker)

/** Headings: exactly one h1 in <main>, and no level skipped going down (h2 → h4). Chat headings checked separately. */
const headingProblems = (page) => page.evaluate(() => {
  const problems = [];
  const hs = [...document.querySelectorAll('main h1, main h2, main h3, main h4, main h5, main h6')];
  const h1s = hs.filter((x) => x.tagName === 'H1');
  if (h1s.length !== 1) problems.push(`main has ${h1s.length} h1 elements`);
  let prev = 0;
  for (const x of hs) {
    const lvl = Number(x.tagName[1]);
    if (prev && lvl > prev + 1) problems.push(`heading level skips from h${prev} to h${lvl} at "${x.textContent.trim().slice(0, 40)}"`);
    prev = lvl;
  }
  for (const img of document.querySelectorAll('img:not([alt])')) problems.push(`img without alt: ${img.src.slice(-40)}`);
  return problems;
});

async function scan(page, info, view, { include } = {}) {
  const store = info.project.name;
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.emulateMedia({ colorScheme: size.colorScheme || 'light' });
    await page.waitForTimeout(150);   // let layout and theme settle
    const r = await h.axeScan(page, info, { store, view: `${view}@${size.name}`, include, baselineView: view, size: size.name });
    expect(r.unexpected.map((v) => `${v.impact} ${v.rule}: ${v.target} — ${v.help}`),
      `new accessibility violations on ${view} at ${size.name} (not in e2e/a11y-baseline.json)`).toEqual([]);
    for (const k of r.matchedKeys) {
      const key = `${store}|${view}`;
      if (!matchedBaseline.has(key)) matchedBaseline.set(key, new Set());
      matchedBaseline.get(key).add(k);
    }
    for (const v of r.known) {
      info.annotations.push({ type: `known a11y ${v.impact}`, description: `${v.rule} @ ${size.name}: ${v.target}` });
    }
  }
  if (!include) expect(await headingProblems(page), `heading/image structure on ${view}`).toEqual([]);
  // Baseline entries for this view must still be seen (otherwise the defect was fixed: remove the entry)
  const expected = h.baselineFor(store, view).map((b) => b.key);
  const seen = matchedBaseline.get(`${store}|${view}`) || new Set();
  expect(expected.filter((k) => !seen.has(k)), `baseline entries for ${view} that no longer occur (remove them)`).toEqual([]);
}

test.describe('axe WCAG 2.2 A/AA scans', () => {
  test('home page', async ({ page }, info) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'All products' })).toBeVisible();
    await page.waitForLoadState('networkidle');
    await scan(page, info, 'home');
  });

  test('product listing (search results and category filter)', async ({ page }, info) => {
    const s = h.STORES[info.project.name];
    await page.goto('/');
    await page.getByLabel('Search products').fill(s.search);
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Search results' })).toBeVisible();
    await page.waitForLoadState('networkidle');
    await scan(page, info, 'listing');
  });

  test('product detail', async ({ page }, info) => {
    const s = h.STORES[info.project.name];
    await page.goto(`/products/${s.product}`);
    await expect(page.getByRole('heading', { level: 1, name: s.productName })).toBeVisible();
    await page.getByRole('button', { name: 'Add to cart', exact: true }).click();
    await expect(page.getByText(`Added 1 × ${s.productName} to your cart.`)).toBeVisible();
    await scan(page, info, 'product');
  });

  test('cart', async ({ page, request }, info) => {
    const store = info.project.name;
    const auth = await h.createCustomer(request, store, 'a11ycart');
    await h.setCartQuantity(request, store, auth, h.STORES[store].product, 2);
    await h.signIn(page, store, auth);
    await page.goto('/cart');
    await expect(page.getByRole('heading', { level: 1, name: /Your cart/ })).toBeVisible();
    await page.waitForLoadState('networkidle');
    await scan(page, info, 'cart');
  });

  test('checkout (shipping and review steps)', async ({ page, request }, info) => {
    const store = info.project.name;
    const s = h.STORES[store];
    const auth = await h.createCustomer(request, store, 'a11ychk');
    await h.setCartQuantity(request, store, auth, s.product, 1);
    await h.signIn(page, store, auth);
    await page.goto('/checkout');
    await expect(page.getByRole('heading', { name: 'Shipping address' })).toBeVisible();
    await page.waitForLoadState('networkidle');
    await scan(page, info, 'checkout-shipping');                       // the India form (India-only stores)
    await h.fillIndianAddress(page, s.address);
    await scan(page, info, 'checkout-shipping-filled');
    await page.getByRole('button', { name: 'Review order' }).click();
    await expect(page.getByRole('heading', { name: 'Review your order' })).toBeVisible();
    await scan(page, info, 'checkout-review');
  });

  test('payment (and its cancel confirmation)', async ({ page, request }, info) => {
    const store = info.project.name;
    const auth = await h.createCustomer(request, store, 'a11ypay');
    const number = await h.placeOrder(request, store, auth);
    try {
      await h.signIn(page, store, auth);
      await page.goto(`/orders/${number}/pay`);
      await expect(page.getByRole('heading', { name: 'Payment' })).toBeVisible();
      await page.waitForLoadState('networkidle');
      await scan(page, info, 'payment');
      await page.getByRole('button', { name: 'Cancel this order' }).click();
      await expect(page.getByRole('group', { name: `Confirm cancelling order ${number}` })).toBeVisible();
      await scan(page, info, 'payment-confirm');
    } finally {
      await h.cancelOrder(request, store, auth, number);
    }
  });

  test('order detail (Phase E)', async ({ page, request }, info) => {
    const store = info.project.name;
    const auth = await h.createCustomer(request, store, 'a11ydetail');
    const number = await h.placeOrder(request, store, auth);
    try {
      await h.signIn(page, store, auth);
      await page.goto(`/orders/${number}`);
      await expect(page.getByRole('heading', { level: 1, name: `Order ${number}` })).toBeVisible();
      await page.waitForLoadState('networkidle');
      await scan(page, info, 'order-detail');
    } finally {
      await h.cancelOrder(request, store, auth, number);
    }
  });

  test('staff fulfilment screens (Phase F)', async ({ page, request }, info) => {
    const store = info.project.name;
    const customer = await h.createCustomer(request, store, 'a11ystaff');
    const number = await h.placeOrder(request, store, customer);
    await h.payOrder(request, store, customer, number);
    await h.signIn(page, store, await h.staffLogin(request, store));
    await page.goto('/staff/orders');
    await expect(page.getByRole('table')).toBeVisible();
    await page.waitForLoadState('networkidle');
    await scan(page, info, 'staff-list');
    await page.goto(`/staff/orders/${number}`);
    await expect(page.getByRole('button', { name: 'Mark as shipped' })).toBeVisible();
    await page.waitForLoadState('networkidle');
    await scan(page, info, 'staff-order');
  });

  for (const [path, heading] of [['/help', 'Help'], ['/shipping', 'Shipping'], ['/returns', 'Returns'], ['/contact', 'Contact us']]) {
    test(`support page ${path} (Phase E)`, async ({ page }, info) => {
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
      await page.waitForLoadState('networkidle');
      await scan(page, info, `support${path.replace('/', '-')}`);
    });
  }

  test('AI chat (Tamil welcome, then an English conversation)', async ({ page }, info) => {
    const s = h.STORES[info.project.name];
    await page.goto('/');
    await page.getByRole('button', { name: `Open chat with ${s.assistant}` }).click();
    const chat = page.getByRole('dialog', { name: s.assistant });
    await expect(chat).toHaveAttribute('lang', 'ta-IN');
    await page.waitForLoadState('networkidle');
    await scan(page, info, 'chat-welcome', { include: '.chat-panel' });
    await chat.getByRole('textbox').fill('Show me something under ₹2,000');
    await chat.getByRole('textbox').press('Enter');
    await expect(chat.locator('.typing')).toHaveCount(0);   // reply arrived (the widget ignores input while busy)
    await expect(chat.locator('.bubble-assistant')).toHaveCount(1);
    await chat.getByRole('textbox').fill('What is your return policy?');
    await chat.getByRole('textbox').press('Enter');
    await expect(chat.locator('.bubble-assistant').last()).toContainText('days');
    await scan(page, info, 'chat-conversation', { include: '.chat-panel' });
  });
});

// axe reports some colour pairs as "incomplete" (text over a gradient, overlapping layers, icon-only buttons).
// This computes the worst-case ratio for those elements directly: text colour (with its opacity) against every
// colour stop of the background gradient, or against the nearest solid background.
const contrastOf = (page, selectors) => page.evaluate((sels) => {
  const parse = (s) => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p[3] ?? 1]; };
  const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };
  const blend = (fg, bg) => [0, 1, 2].map((i) => fg[i] * fg[3] + bg[i] * (1 - fg[3]));
  const out = [];
  for (const sel of sels) {
    for (const el of document.querySelectorAll(sel)) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height || getComputedStyle(el).visibility === 'hidden') continue;
      let opacity = 1; let bgs = null;
      for (let n = el; n; n = n.parentElement) {
        const s = getComputedStyle(n);
        opacity *= Number(s.opacity);
        if (s.backgroundImage && s.backgroundImage.includes('gradient')) { bgs = [...s.backgroundImage.matchAll(/rgba?\([^)]+\)/g)].map((m) => parse(m[0])); break; }
        const bg = parse(s.backgroundColor);
        if (bg && bg[3] > 0.99) { bgs = [bg]; break; }
      }
      bgs = bgs || [[255, 255, 255, 1]];
      const fg = parse(getComputedStyle(el).color); fg[3] *= opacity;
      const st = getComputedStyle(el);
      const large = parseFloat(st.fontSize) >= 24 || (parseFloat(st.fontSize) >= 18.66 && Number(st.fontWeight) >= 700);
      const worst = Math.min(...bgs.map((bg) => ratio(blend(fg, bg), bg)));
      out.push({ sel, text: (el.getAttribute('aria-label') || el.textContent).trim().slice(0, 30), ratio: Math.round(worst * 100) / 100, needed: large ? 3 : 4.5 });
    }
  }
  return out;
}, selectors);

test('supplementary contrast check for elements axe could not decide', async ({ page }, info) => {
  const s = h.STORES[info.project.name];
  for (const scheme of ['light', 'dark']) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'All products' })).toBeVisible();
    await page.getByRole('button', { name: `Add ${s.productName} to cart` }).first().click();   // non-empty cart badge
    await expect(page.locator('.cart-count:not(.cart-count-empty)')).toBeVisible();
    const page1 = await contrastOf(page, ['.hero-eyebrow', '.hero h1', '.hero-copy > p', '.btn-on-hero', '.cart-count', '.launcher-label']);
    await page.getByRole('button', { name: `Open chat with ${s.assistant}` }).click();
    await page.getByRole('dialog', { name: s.assistant }).getByRole('textbox').fill('hi');
    const chat = await contrastOf(page, ['.chat-header .icon-btn', '.chat-header h2', '.chat-header p', '.chat-empty > p', '.chat-empty .chip', '.lang-note', '.chat-footer label']);
    const all = [...page1, ...chat];
    await info.attach(`contrast-${scheme}.json`, { body: JSON.stringify(all, null, 2), contentType: 'application/json' });
    expect(all.length).toBeGreaterThan(8);
    expect(all.filter((x) => x.ratio < x.needed).map((x) => `${scheme} ${x.sel} "${x.text}": ${x.ratio}:1 < ${x.needed}:1`)).toEqual([]);
    // Regression for A-1 (fixed in Phase D): white text on the accent (badge, launcher) meets 4.5:1 in both themes.
    for (const x of all.filter((y) => ['.cart-count', '.launcher-label'].includes(y.sel))) {
      expect(x.ratio, `${scheme} ${x.sel} contrast`).toBeGreaterThanOrEqual(4.5);
    }
  }
});

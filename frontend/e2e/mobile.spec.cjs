// Mobile responsiveness: every main screen of each storefront (project) at four viewports.
// Checks page-level horizontal overflow, elements outside the viewport, overlapping controls, clipped text, form
// field usability, navigation, the floating chat launcher covering controls, and dialogs/overlays fitting the screen.
// Intentional scrolling INSIDE a component (an element whose own box fits the viewport) is not counted as overflow.
const { test } = require('@playwright/test');
const h = require('./support/helpers.cjs');

const { expect } = h;

for (const vp of h.VIEWPORTS) {
  test.describe(`${vp.name} ${vp.width}×${vp.height}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height }, isMobile: vp.isMobile, hasTouch: vp.isMobile });

    const fits = async (page, where) => {
      expect(await h.layoutProblems(page), `layout problems on ${where}`).toEqual([]);
      expect(await h.overlappingControls(page), `overlapping controls on ${where}`).toEqual([]);
    };
    // Floating layers (the chat launcher, toasts) must never completely hide a control the shopper needs.
    // (Focus scrolling under the sticky header is covered separately in keyboard.spec.cjs.)
    const notObscured = async (locator) => expect(await h.obscuredWhenFocused(locator, { center: true })).toBeNull();

    test('home page and main navigation', async ({ page }, info) => {
      const s = h.STORES[info.project.name];
      await page.goto('/');
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      await expect(page.getByRole('heading', { name: 'All products' })).toBeVisible();
      await expect(page.getByRole('button', { name: /^Add .* to cart$/ }).first()).toBeVisible();   // products rendered
      await page.waitForLoadState('networkidle');
      await fits(page, 'home');
      const nav = page.getByRole('navigation', { name: 'Main' });
      for (const name of ['Shop', 'Sign in', 'Cart, 0 items', 'Help']) {
        const item = nav.getByRole(name === 'Help' ? 'button' : 'link', { name, exact: true });
        await expect(item).toBeVisible();
        expect((await h.insideViewport(item)).inside, `${name} inside the viewport`).toBe(true);
        const box = await item.boundingBox();
        expect(box.height, `${name} target height`).toBeGreaterThanOrEqual(24);   // WCAG 2.2 SC 2.5.8 minimum
      }
      await nav.getByRole('link', { name: 'Cart, 0 items' }).click();
      await expect(page).toHaveURL(/\/cart$/);
      await nav.getByRole('link', { name: 'Sign in' }).click();
      await expect(page).toHaveURL(/\/account$/);
      await page.getByRole('link', { name: `${s.name} home` }).click();
      await expect(page).toHaveURL(/\/$/);
      // K-1 regression: the page's scroll padding keeps scrolled-to / focused content clear of the sticky header
      const pad = await page.evaluate(() => ({ padding: parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop) || 0,
        header: document.querySelector('.site-header').getBoundingClientRect().height }));
      expect(pad.padding, `scroll-padding-top ${pad.padding}px covers the ${pad.header}px sticky header`).toBeGreaterThanOrEqual(pad.header + 8);
      info.annotations.push({ type: 'measure', description: `${vp.name}: sticky header ${Math.round(pad.header)}px, scroll-padding-top ${pad.padding}px` });
      // Footer content is reachable above the chat launcher
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      await notObscured(page.locator('.footer-note'));
    });

    test('search and product listing', async ({ page }, info) => {
      const s = h.STORES[info.project.name];
      await page.goto('/');
      const search = page.getByLabel('Search products');
      expect((await h.insideViewport(search)).insideX, 'search box fits the width').toBe(true);
      await search.fill(s.search);
      await page.getByRole('button', { name: 'Search', exact: true }).click();
      await expect(page.getByRole('heading', { name: 'Search results' })).toBeVisible();
      await expect(page.getByRole('link', { name: s.productName, exact: true }).first()).toBeVisible();
      await fits(page, 'search results');
      const chips = page.getByRole('group', { name: 'Filter by category' });
      await expect(chips).toBeVisible();
      await page.getByRole('button', { name: 'Clear search ✕' }).click();
      const firstCategory = chips.getByRole('button').nth(1);
      const category = (await firstCategory.textContent()).trim();
      await firstCategory.click();
      await expect(firstCategory).toHaveAttribute('aria-pressed', 'true');
      await page.waitForLoadState('networkidle');   // the filtered list has replaced the full one
      await expect(page.getByRole('heading', { name: category, level: 2 })).toBeVisible();
      await fits(page, `category ${category}`);
      // Every product card's add button is usable (not hidden behind the launcher)
      const addButtons = await page.getByRole('button', { name: /^Add .* to cart$/ }).all();
      for (const btn of addButtons) await notObscured(btn);
      // The "added" toast fits the screen and does not hide the chat launcher or the page's controls
      await addButtons[0].click();
      const toast = page.locator('.toast');
      await expect(toast).toContainText('to your cart');
      expect((await h.insideViewport(toast)).inside, 'toast inside the viewport').toBe(true);
      await expect(toast.getByRole('link', { name: 'View cart' })).toBeVisible();
      expect(await h.obscuredWhenFocused(page.locator('.chat-launcher'))).toBeNull();
      await fits(page, 'listing with toast');
    });

    test('product detail page', async ({ page }, info) => {
      const s = h.STORES[info.project.name];
      await page.goto(`/products/${s.product}`);
      await expect(page.getByRole('heading', { level: 1, name: s.productName })).toBeVisible();
      await fits(page, 'product detail');
      await notObscured(page.getByRole('button', { name: 'Add to cart', exact: true }));
      const img = page.locator('main img, main svg').first();
      if (await img.count()) expect((await img.boundingBox()).width).toBeLessThanOrEqual(vp.width);
      await page.getByRole('button', { name: 'Add to cart', exact: true }).click();
      await expect(page.getByText(`Added 1 × ${s.productName} to your cart.`)).toBeVisible();
      await expect(page.getByRole('link', { name: 'Cart, 1 item' })).toBeVisible();
      await fits(page, 'product detail after adding');
    });

    test('shopping cart', async ({ page, request }, info) => {
      const store = info.project.name;
      const s = h.STORES[store];
      const auth = await h.createCustomer(request, store, 'cart');
      await h.setCartQuantity(request, store, auth, s.product, 2);
      await h.signIn(page, store, auth);
      await page.goto('/cart');
      await expect(page.getByRole('heading', { level: 1, name: /Your cart/ })).toBeVisible();
      await fits(page, 'cart');
      const qty = page.getByLabel(`Quantity for ${s.productName}`);
      await notObscured(qty);
      await qty.selectOption('1');
      await expect(page.getByRole('link', { name: 'Cart, 1 item' })).toBeVisible();
      await notObscured(page.getByRole('button', { name: `Remove ${s.productName}` }));
      const checkout = page.getByRole('button', { name: 'Checkout', exact: true });
      await notObscured(checkout);
      await checkout.click();
      await expect(page).toHaveURL(/\/checkout$/);
    });

    test('checkout steps and form fields', async ({ page, request }, info) => {
      const store = info.project.name;
      const s = h.STORES[store];
      const auth = await h.createCustomer(request, store, 'checkout');
      await h.setCartQuantity(request, store, auth, s.product, 1);
      await h.signIn(page, store, auth);
      await page.goto('/checkout');
      await expect(page.getByRole('heading', { name: 'Shipping address' })).toBeVisible();
      await fits(page, 'checkout shipping step (India)');
      // Each field must show a realistic value in full (no scrolling inside the box) and be a usable target.
      const fields = [['Full name', 'E2E Shopper Jr'], ['Address line 1', s.address.line1], ['Address line 2 / Landmark (optional)', 'Near the bus stand'],
        ['City / Town', s.address.city], ['State / union territory', null], ['PIN code', s.address.postal_code], ['Mobile number', s.address.phone]];
      for (const [label, sample] of fields) {
        const f = page.getByLabel(label, { exact: typeof label === 'string' });
        await expect(f).toBeEditable();
        const box = await f.boundingBox();
        expect(box.width, `${label} width`).toBeGreaterThanOrEqual(44);
        expect(box.height, `${label} target height`).toBeGreaterThanOrEqual(24);
        if (sample) {
          await f.fill(sample);
          const [sw, cw] = await f.evaluate((el) => [el.scrollWidth, el.clientWidth]);
          // (M-1, fixed in Phase D: the ZIP field was 84px at 768px and cut off a ZIP+4.)
          expect(sw, `"${sample}" fits in ${label} (${sw} > ${cw})`).toBeLessThanOrEqual(cw + 1);
        } else {
          expect(await f.evaluate((el) => el.scrollWidth <= el.clientWidth + 1), `${label} shows its value`).toBe(true);
        }
        expect((await h.insideViewport(f)).rect.right).toBeLessThanOrEqual(vp.width);
        await notObscured(f);
      }
      await h.fillIndianAddress(page, s.address);
      await notObscured(page.getByRole('button', { name: 'Review order' }));
      await page.getByRole('button', { name: 'Review order' }).click();
      await expect(page.getByRole('heading', { name: 'Review your order' })).toBeVisible();
      await fits(page, 'checkout review step');
      const place = page.getByRole('button', { name: /^Place order · / });
      await notObscured(place);
      await notObscured(page.getByRole('button', { name: /Edit|Back|Change/ }).first());
    });

    test('payment page and cancel confirmation', async ({ page, request }, info) => {
      const store = info.project.name;
      const auth = await h.createCustomer(request, store, 'pay');
      const number = await h.placeOrder(request, store, auth);
      try {
        await h.signIn(page, store, auth);
        await page.goto(`/orders/${number}/pay`);
        await expect(page.getByRole('heading', { name: 'Payment' })).toBeVisible();
        await fits(page, 'payment');
        await notObscured(page.getByRole('button', { name: /^Pay .* \(test\)$/ }));
        await notObscured(page.getByRole('button', { name: 'Cancel this order' }));
        await page.getByRole('button', { name: 'Cancel this order' }).click();
        const confirm = page.getByRole('group', { name: `Confirm cancelling order ${number}` });
        await expect(confirm).toBeVisible();
        await fits(page, 'payment cancel confirmation');
        await notObscured(confirm.getByRole('button', { name: `Yes, cancel order ${number}` }));
        await notObscured(confirm.getByRole('button', { name: 'Keep my order' }));
        await confirm.getByRole('button', { name: `Yes, cancel order ${number}` }).click();
        await expect(page.getByRole('heading', { name: 'Order cancelled' })).toBeVisible();
      } finally {
        await h.cancelOrder(request, store, auth, number);
      }
    });

    test('order detail page (Phase E)', async ({ page, request }, info) => {
      const store = info.project.name;
      const auth = await h.createCustomer(request, store, 'detail');
      const number = await h.placeOrder(request, store, auth);
      try {
        await h.signIn(page, store, auth);
        await page.goto(`/orders/${number}`);
        await expect(page.getByRole('heading', { level: 1, name: `Order ${number}` })).toBeVisible();
        await expect(page.getByRole('list', { name: 'Order progress' })).toBeVisible();
        await fits(page, 'order detail');
        await notObscured(page.getByRole('link', { name: 'Pay now' }));
        await notObscured(page.getByRole('link', { name: h.STORES[store].productName }));
      } finally {
        await h.cancelOrder(request, store, auth, number);
      }
    });

    test('staff fulfilment screens (Phase F)', async ({ page, request }, info) => {
      const store = info.project.name;
      const customer = await h.createCustomer(request, store, 'mstaff');
      const number = await h.placeOrder(request, store, customer);
      await h.payOrder(request, store, customer, number);
      await h.signIn(page, store, await h.staffLogin(request, store));
      await page.goto('/staff/orders');
      await expect(page.getByRole('table')).toBeVisible();
      await page.waitForLoadState('networkidle');
      await fits(page, 'staff list');   // the wide table scrolls inside .table-scroll (intentional), never the page
      await page.goto(`/staff/orders/${number}`);
      await expect(page.getByRole('button', { name: 'Mark as shipped' })).toBeVisible();
      await fits(page, 'staff order');
      for (const label of ['Carrier', 'Tracking number']) await notObscured(page.getByLabel(label));
      await notObscured(page.getByRole('button', { name: 'Mark as shipped' }));
    });

    test('support pages (Phase E)', async ({ page }) => {
      for (const [path, heading] of [['/help', 'Help'], ['/shipping', 'Shipping'], ['/returns', 'Returns'], ['/contact', 'Contact us']]) {
        await page.goto(path);
        await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
        await page.waitForLoadState('networkidle');
        await fits(page, path);
      }
      await notObscured(page.getByRole('link', { name: /@/ }));   // the support e-mail on the contact page
    });

    test('chat widget, language selection and Tamil text', async ({ page }, info) => {
      const s = h.STORES[info.project.name];
      await page.goto('/');
      const launcher = page.getByRole('button', { name: `Open chat with ${s.assistant}` });
      expect((await h.insideViewport(launcher)).inside, 'launcher inside the viewport').toBe(true);
      await launcher.click();
      const chat = page.getByRole('dialog', { name: s.assistant });
      await expect(chat).toHaveAttribute('lang', 'ta-IN');
      const panel = await h.insideViewport(chat);
      expect(panel.inside, `chat panel fits the screen ${JSON.stringify(panel)}`).toBe(true);
      await fits(page, 'chat open');
      // Tamil renders with a real font (no fallback boxes) and is not clipped inside the panel
      const tamilOk = await page.evaluate(() => document.fonts.check('16px sans-serif', 'வணக்கம்'));
      expect(tamilOk, 'a font can render Tamil').toBe(true);
      const welcome = chat.locator('.chat-empty p');
      await expect(welcome).toContainText('வணக்கம்');
      const wb = await welcome.boundingBox();
      expect(wb.width).toBeGreaterThan(40);
      expect(await h.clippedText(page, '.chat-panel')).toEqual([]);
      for (const control of [chat.getByRole('button', { name: 'அரட்டையை மூடு' }), chat.getByRole('textbox'),
        chat.getByRole('button', { name: 'அனுப்பு', exact: true }), chat.getByTestId('conversation-language')]) {
        expect((await h.insideViewport(control)).inside).toBe(true);
      }
      // Suggestions wrap inside the panel instead of overflowing it
      for (const chip of await chat.locator('.chat-empty .chip').all()) {
        const b = await chip.boundingBox();
        expect(b.x + b.width, 'suggestion inside the panel').toBeLessThanOrEqual(panel.rect.right + 1);
      }
      // Switch language, then converse
      await chat.getByTestId('conversation-language').selectOption('en');
      await expect(chat).toHaveAttribute('lang', 'en-IN');
      await chat.getByRole('textbox').fill('What is your return policy?');
      await chat.getByRole('textbox').press('Enter');
      const reply = chat.locator('.bubble-assistant').last();
      await expect(reply).toContainText('days');
      expect((await reply.boundingBox()).x + (await reply.boundingBox()).width).toBeLessThanOrEqual(panel.rect.right + 1);
      await chat.getByTestId('conversation-language').selectOption('ta');
      await chat.getByRole('textbox').fill('திருப்பி அனுப்பும் கொள்கை என்ன?');
      await chat.getByRole('textbox').press('Enter');
      await expect(chat.locator('.bubble-user').last()).toContainText('திருப்பி');
      await expect(chat.locator('.bubble-assistant').nth(1)).toBeVisible();
      expect(await h.clippedText(page, '.chat-panel')).toEqual([]);
      await fits(page, 'chat conversation');
      await chat.getByRole('button', { name: 'Close chat' }).or(chat.getByRole('button', { name: 'அரட்டையை மூடு' })).click();
      await expect(chat).toBeHidden();
      await expect(launcher).toBeVisible();
    });
  });
}

// M-1 regression (fixed in Phase D): at every width the checkout's address row shows a full PIN code, a long Indian
// city name and the selected state's full name.
test('checkout PIN code, city and state fit at every width from phone to desktop', async ({ page, request }, info) => {
  const store = info.project.name;
  const s = h.STORES[store];
  const auth = await h.createCustomer(request, store, 'zipsweep');
  await h.setCartQuantity(request, store, auth, s.product, 1);
  await h.signIn(page, store, auth);
  await page.goto('/checkout');
  await expect(page.getByRole('heading', { name: 'Shipping address' })).toBeVisible();
  await page.getByLabel('PIN code').fill('695001');
  await page.getByLabel('City / Town').fill('Thiruvananthapuram');
  await page.getByLabel('State / union territory').selectOption('TN');
  const tooSmall = [];
  for (const width of [375, 390, 430, 600, 721, 768, 820, 900, 1000, 1024, 1100, 1180, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    for (const label of ['PIN code', 'City / Town', 'State / union territory']) {
      const [sw, cw] = await page.getByLabel(label).evaluate((el) => [el.scrollWidth, el.clientWidth]);
      if (sw > cw + 1) tooSmall.push(`${width}px: ${label} needs ${sw}px, shows ${cw}px`);
    }
  }
  expect(tooSmall).toEqual([]);
});

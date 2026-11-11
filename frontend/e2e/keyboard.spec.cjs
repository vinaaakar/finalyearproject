// Keyboard-only use of each storefront (project): Tab / Shift+Tab order, Enter and Space activation, visible focus,
// no keyboard traps, the chat dialog without a mouse, and a complete checkout without a mouse.
// The Phase C findings K-1…K-5 were fixed in Phase D; these are now ordinary assertions (regression tests).
const { test } = require('@playwright/test');
const h = require('./support/helpers.cjs');

const { expect } = h;

/** Describe the focused element: role-ish tag, accessible-ish name, whether its focus indicator is visible. */
const focused = (page) => page.evaluate(() => {
  const el = document.activeElement;
  if (!el || el === document.body) return { tag: 'body', name: '', indicator: false, inChat: false };
  const s = getComputedStyle(el);
  const after = getComputedStyle(el, '::after');
  const outline = (st) => st.outlineStyle !== 'none' && parseFloat(st.outlineWidth) > 0;
  const r = el.getBoundingClientRect();
  return {
    tag: el.tagName.toLowerCase(),
    name: (el.getAttribute('aria-label') || el.textContent || el.getAttribute('placeholder') || el.id || '').trim().replace(/\s+/g, ' ').slice(0, 60),
    indicator: outline(s) || s.boxShadow !== 'none' || outline(after),
    rendered: r.width > 0 && r.height > 0,
    inChat: !!el.closest('.chat-panel'),
    inMain: !!el.closest('main'),
  };
});

/** Press Tab (or Shift+Tab) until `match(focusInfo)` is true; fails after `max` presses. */
async function tabTo(page, match, { back = false, max = 80 } = {}) {
  for (let i = 0; i < max; i += 1) {
    await page.keyboard.press(back ? 'Shift+Tab' : 'Tab');
    const f = await focused(page);
    if (match(f)) return f;
  }
  throw new Error(`focus never reached the target after ${max} ${back ? 'Shift+Tab' : 'Tab'} presses`);
}

test.describe('keyboard (desktop 1280×800)', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('Tab and Shift+Tab: skip link, header order, visible focus, no trap', async ({ page }, info) => {
    const s = h.STORES[info.project.name];
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'All products' })).toBeVisible();
    await page.keyboard.press('Tab');
    let f = await focused(page);
    expect(f.name).toBe('Skip to content');
    expect((await h.insideViewport(page.locator('.skip-link'))).inside, 'skip link becomes visible on focus').toBe(true);
    const forward = [f.name];
    for (let i = 0; i < 5; i += 1) { await page.keyboard.press('Tab'); forward.push((await focused(page)).name); }
    expect(forward).toEqual(['Skip to content', `${s.name} home`, 'Shop', 'Sign in', 'Cart, 0 items', 'Help']);
    const backward = [];
    for (let i = 0; i < 5; i += 1) { await page.keyboard.press('Shift+Tab'); backward.push((await focused(page)).name); }
    expect(backward).toEqual(forward.slice(0, 5).reverse());

    // Skip link moves the keyboard start point into the main content
    await page.keyboard.press('Enter');
    await page.keyboard.press('Tab');
    expect((await focused(page)).inMain, 'Tab after "Skip to content" lands inside <main>').toBe(true);

    // Walk every stop on the page: each is rendered, visibly focused, and focus eventually wraps (no trap)
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'All products' })).toBeVisible();
    const stops = [];
    for (let i = 0; i < 150; i += 1) {
      await page.keyboard.press('Tab');
      f = await focused(page);
      if (f.tag === 'body' || (i > 0 && f.name === 'Skip to content')) break;
      stops.push(f);
    }
    expect(stops.length, 'reached the end of the page and wrapped (no keyboard trap)').toBeLessThan(150);
    expect(stops.filter((x) => !x.rendered).map((x) => x.name), 'focus never lands on an invisible element').toEqual([]);
    expect(stops.filter((x) => !x.indicator).map((x) => `${x.tag} "${x.name}"`), 'every focused control shows a focus indicator').toEqual([]);
    expect(stops.map((x) => x.name)).toContain(`Open chat with ${s.assistant}`);
  });

  test('Enter and Space activate links, buttons and toggles', async ({ page }, info) => {
    const s = h.STORES[info.project.name];
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'All products' })).toBeVisible();
    // Space toggles a category filter chip
    const chip = page.getByRole('group', { name: 'Filter by category' }).getByRole('button').nth(1);
    await chip.focus();
    await page.keyboard.press('Space');
    await expect(chip).toHaveAttribute('aria-pressed', 'true');
    const all = page.getByRole('group', { name: 'Filter by category' }).getByRole('button').first();
    await all.focus();
    await page.keyboard.press('Space');
    await expect(all).toHaveAttribute('aria-pressed', 'true');
    // Enter submits the search from the search box
    await page.getByLabel('Search products').focus();
    await page.keyboard.type(s.search);
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { name: 'Search results' })).toBeVisible();
    // Space on a product card's add button
    await page.getByRole('button', { name: `Add ${s.productName} to cart` }).first().focus();
    await page.keyboard.press('Space');
    await expect(page.locator('.toast')).toContainText(`Added ${s.productName} to your cart.`);
    await expect(page.getByRole('link', { name: 'Cart, 1 item' })).toBeVisible();
    // Enter follows a product link
    await page.getByRole('link', { name: s.productName, exact: true }).first().focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { level: 1, name: s.productName })).toBeVisible();
    // Enter on the product page's Add to cart
    await page.getByRole('button', { name: 'Add to cart', exact: true }).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByText(`Added 1 × ${s.productName} to your cart.`)).toBeVisible();
    await expect(page.getByRole('link', { name: 'Cart, 2 items' })).toBeVisible();
  });

  test('chat can be opened, used and closed without a mouse', async ({ page }, info) => {
    const s = h.STORES[info.project.name];
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'All products' })).toBeVisible();
    await tabTo(page, (f) => f.name === `Open chat with ${s.assistant}`, { back: true, max: 5 });
    await page.keyboard.press('Enter');
    const chat = page.getByRole('dialog', { name: s.assistant });
    await expect(chat).toBeVisible();
    await expect(chat.getByRole('textbox')).toBeFocused();   // focus moves into the dialog
    await page.keyboard.type('What is your return policy?');
    await page.keyboard.press('Enter');
    await expect(chat.locator('.bubble-assistant').last()).toContainText('days');
    // Keyboard reaches the language select and changes it (type-to-select: on macOS the arrow keys open the list)
    const select = chat.getByTestId('conversation-language');
    await tabTo(page, (f) => f.tag === 'select', { max: 10 });
    await expect(select).toBeFocused();
    await page.keyboard.type('E');
    await expect(select).toHaveValue('en');
    await expect(chat).toHaveAttribute('lang', 'en-IN');
    // Every control inside the open chat shows focus
    await chat.getByRole('textbox').focus();
    const chatStops = [];
    for (let i = 0; i < 8; i += 1) { await page.keyboard.press('Tab'); const f = await focused(page); if (!f.inChat) break; chatStops.push(f); }
    expect(chatStops.filter((x) => !x.indicator).map((x) => x.name), 'chat controls show focus').toEqual([]);

    const launcher = page.getByRole('button', { name: `Open chat with ${s.assistant}` });
    // K-2: Escape closes the chat (here from the message box) …  K-3: … and focus returns to the launcher
    await chat.getByRole('textbox').focus();
    await page.keyboard.press('Escape');
    await expect(chat).toBeHidden();
    await expect(launcher).toBeFocused();
    // The conversation is kept: reopening shows it again
    await page.keyboard.press('Enter');
    await expect(chat.getByRole('textbox')).toBeFocused();   // the widget moves focus in on the next tick: wait for it
    await expect(chat.locator('.bubble-assistant').last()).toContainText('days');

    // Close with the keyboard via the close button → focus returns to the launcher
    await chat.getByRole('textbox').focus();
    await tabTo(page, (f) => f.inChat && f.tag === 'button' && /close|மூடு|बंद/i.test(f.name), { back: true, max: 15 });
    await expect(chat.locator('.chat-header .icon-btn')).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(chat).toBeHidden();
    await expect(launcher).toBeFocused();

    // Opened from the header's Help button → Escape returns focus to Help (the control that opened it)
    const help = page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'Help' });
    await help.focus();
    await page.keyboard.press('Enter');
    await expect(chat.getByRole('textbox')).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(chat).toBeHidden();
    await expect(help).toBeFocused();

    // Escape with the chat closed changes nothing on the page
    await page.keyboard.press('Escape');
    await expect(help).toBeFocused();
    await expect(launcher).toBeVisible();
  });

  test('checkout can be completed with the keyboard alone', async ({ page, request }, info) => {
    const store = info.project.name;
    const s = h.STORES[store];
    const auth = await h.createCustomer(request, store, 'kbd');
    await h.setCartQuantity(request, store, auth, s.product, 1);
    await h.signIn(page, store, auth);
    let number = null;
    try {
      await page.goto('/cart');
      await expect(page.getByRole('heading', { level: 1, name: /Your cart/ })).toBeVisible();
      await tabTo(page, (f) => f.name === 'Checkout');
      await page.keyboard.press('Enter');
      await expect(page.getByRole('heading', { name: 'Shipping address' })).toBeVisible();
      // India-only: "Delivering to India" (no country choice). Name is prefilled from the account; Tab through the form and type like a keyboard user
      await tabTo(page, (f) => f.tag === 'input' && f.inMain);
      await expect(page.getByLabel('Full name')).toBeFocused();
      await page.keyboard.press('Tab');
      await expect(page.getByLabel('Address line 1')).toBeFocused();
      await page.keyboard.type(s.address.line1);
      await page.keyboard.press('Tab');
      await expect(page.getByLabel('Address line 2 / Landmark (optional)')).toBeFocused();
      await page.keyboard.press('Tab');
      await expect(page.getByLabel('City / Town')).toBeFocused();
      await page.keyboard.type(s.address.city);
      await page.keyboard.press('Tab');
      await expect(page.getByLabel('State / union territory')).toBeFocused();
      await page.keyboard.type(s.address.regionName);   // type-to-select by the state's name on a focused <select>
      await expect(page.getByLabel('State / union territory')).toHaveValue(s.address.region);
      await page.keyboard.press('Tab');
      await expect(page.getByLabel('PIN code')).toBeFocused();
      await page.keyboard.type(s.address.postal_code);
      await page.keyboard.press('Tab');
      await expect(page.getByLabel('Mobile number')).toBeFocused();
      await page.keyboard.type(s.address.phone);
      // India: delivery is priced for the address just typed — the option appears once the server has quoted it.
      await expect(page.getByRole('radio', { name: /^Standard delivery/ })).toBeVisible();
      // Shipping method radios: arrow keys move the choice
      await page.keyboard.press('Tab');
      const radio = await focused(page);
      expect(radio.tag).toBe('input');
      await page.keyboard.press('Enter');   // Enter inside the form submits it → review step
      await expect(page.getByRole('heading', { name: 'Review your order' })).toBeVisible();
      await tabTo(page, (f) => f.name.startsWith('Place order'));
      await page.keyboard.press('Enter');
      await expect(page).toHaveURL(/\/orders\/[A-Z]{2}-\d{5}\/pay$/);
      number = page.url().match(/[A-Z]{2}-\d{5}/)[0];
      await expect(page.getByRole('heading', { name: 'Payment' })).toBeVisible();
      // Cancel with the keyboard, through the confirmation
      await tabTo(page, (f) => f.name === 'Cancel this order');
      await page.keyboard.press('Enter');
      const confirm = page.getByRole('group', { name: `Confirm cancelling order ${number}` });
      await expect(confirm).toBeVisible();
      // K-5: focus moves into the confirmation (its group), with a visible indicator
      await expect(confirm).toBeFocused();
      expect((await focused(page)).indicator, 'confirmation shows focus').toBe(true);
      // "Keep my order" closes it and returns focus to "Cancel this order"
      await tabTo(page, (f) => f.name === 'Keep my order', { max: 3 });
      await page.keyboard.press('Enter');
      await expect(confirm).toBeHidden();
      await expect(page.getByRole('button', { name: 'Cancel this order' })).toBeFocused();
      // Reopen and confirm: the first Tab from the confirmation reaches "Yes, cancel"
      await page.keyboard.press('Enter');
      await expect(confirm).toBeFocused();
      await page.keyboard.press('Tab');
      expect((await focused(page)).name).toBe(`Yes, cancel order ${number}`);
      await page.keyboard.press('Space');
      await expect(page.getByRole('heading', { name: 'Order cancelled' })).toBeVisible();
    } finally {
      if (number) await h.cancelOrder(request, store, auth, number);
    }
  });
});

test.describe('keyboard focus visibility while moving backwards', () => {
  for (const vp of [h.VIEWPORTS[1], h.VIEWPORTS[3]]) {
    test(`Shift+Tab never leaves focus completely hidden (${vp.name} ${vp.width}×${vp.height})`, async ({ page, request }, info) => {
      const store = info.project.name;
      const s = h.STORES[store];
      await page.setViewportSize({ width: vp.width, height: vp.height });
      const auth = await h.createCustomer(request, store, 'kbdback');
      await h.setCartQuantity(request, store, auth, s.product, 1);
      await h.signIn(page, store, auth);
      await page.goto('/checkout');
      await h.fillIndianAddress(page, s.address);
      await page.getByRole('button', { name: 'Review order' }).click();
      await expect(page.getByRole('heading', { name: 'Review your order' })).toBeVisible();
      // From the bottom of the page, walk backwards through every control up to the header
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      await page.locator('.site-footer').evaluate((el) => { el.setAttribute('tabindex', '-1'); el.focus(); el.removeAttribute('tabindex'); });
      const hidden = [];
      for (let i = 0; i < 40; i += 1) {
        await page.keyboard.press('Shift+Tab');
        const f = await focused(page);
        if (f.tag === 'body' || f.name === 'Skip to content') break;
        if (f.inChat) continue;
        const why = await page.evaluate(() => {
          const el = document.activeElement;
          if (el.closest('.site-header')) return null;
          const r = el.getBoundingClientRect();
          const pts = [[r.left + r.width / 2, r.top + r.height / 2], [r.left + 2, r.top + 2], [r.right - 2, r.bottom - 2]];
          const hits = pts.map(([x, y]) => document.elementFromPoint(x, y));
          return hits.every((hit) => hit && hit !== el && !el.contains(hit)) ? `"${(el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 40)}" under ${hits[0].closest('header, .chat-launcher, .toast-region')?.className || hits[0].className}` : null;
        });
        if (why) hidden.push(why);
      }
      // K-1 (fixed): nothing focused may be completely hidden, including by the sticky header
      expect(hidden, 'focused controls completely hidden while moving backwards').toEqual([]);
    });
  }
});

test.describe('phone: full-screen chat dialog focus', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  const background = (page) => page.evaluate(() => {
    const panel = document.querySelector('.chat-panel');
    const root = (panel || document.querySelector('.chat-launcher')).parentElement;
    return [...root.children].filter((el) => el !== panel).map((el) => ({ tag: el.tagName.toLowerCase(), cls: el.className, inert: el.inert }));
  });

  test('full-screen chat is modal: Tab stays inside, background is inert, restored on close', async ({ page }, info) => {
    const s = h.STORES[info.project.name];
    await page.goto('/');
    const launcher = page.getByRole('button', { name: `Open chat with ${s.assistant}` });
    await launcher.click();
    const chat = page.getByRole('dialog', { name: s.assistant });
    await expect(chat.getByRole('textbox')).toBeFocused();
    const panel = await h.insideViewport(chat);
    expect(panel.rect.left <= 0 && panel.rect.right >= 389, 'chat covers the whole phone screen').toBe(true);
    await expect(chat).toHaveAttribute('aria-modal', 'true');
    const bg = await background(page);
    expect(bg.length).toBeGreaterThanOrEqual(4);   // skip link, header, main, footer, toast region
    expect(bg.filter((x) => !x.inert), 'every background region is inert').toEqual([]);
    // Tab / Shift+Tab never reach the page behind
    const escaped = [];
    for (const key of ['Tab', 'Shift+Tab']) {
      await chat.getByRole('textbox').focus();
      for (let i = 0; i < 25; i += 1) {
        await page.keyboard.press(key);
        const f = await focused(page);
        if (!f.inChat && f.tag !== 'body') escaped.push(`${key} → ${f.tag} "${f.name}"`);
      }
    }
    expect(escaped, 'focus escaped the modal chat').toEqual([]);
    // Background controls cannot be activated programmatically-by-focus either
    await page.locator('.site-header a').first().focus();
    expect((await focused(page)).inChat || (await focused(page)).tag === 'body', 'inert header link cannot take focus').toBe(true);
    // Closing restores the page and returns focus to the launcher
    await chat.getByRole('textbox').focus();
    await page.keyboard.press('Escape');
    await expect(chat).toBeHidden();
    await expect(launcher).toBeFocused();
    expect((await background(page)).filter((x) => x.inert), 'background restored after closing').toEqual([]);
    await page.getByRole('link', { name: 'Shop', exact: true }).click();   // background is interactive again
    await expect(page).toHaveURL(/\/$/);
  });

  test('widening the screen while the chat is open makes it non-modal again', async ({ page }, info) => {
    const s = h.STORES[info.project.name];
    await page.goto('/');
    await page.getByRole('button', { name: `Open chat with ${s.assistant}` }).click();
    const chat = page.getByRole('dialog', { name: s.assistant });
    await expect(chat).toHaveAttribute('aria-modal', 'true');
    await page.setViewportSize({ width: 1280, height: 800 });
    await expect(chat).toHaveAttribute('aria-modal', 'false');
    await expect.poll(async () => (await background(page)).filter((x) => x.inert).length).toBe(0);
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(chat).toHaveAttribute('aria-modal', 'true');
    await expect.poll(async () => (await background(page)).filter((x) => !x.inert).length).toBe(0);
  });
});

test.describe('desktop: floating chat stays non-modal', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('page stays usable beside the open chat', async ({ page }, info) => {
    const s = h.STORES[info.project.name];
    await page.goto('/');
    await page.getByRole('button', { name: `Open chat with ${s.assistant}` }).click();
    const chat = page.getByRole('dialog', { name: s.assistant });
    await expect(chat).toHaveAttribute('aria-modal', 'false');
    const inert = await page.evaluate(() => [...document.querySelector('.chat-panel').parentElement.children].filter((el) => el.inert).length);
    expect(inert, 'nothing inert on desktop').toBe(0);
    await page.getByRole('link', { name: 'Cart, 0 items' }).click();
    await expect(page).toHaveURL(/\/cart$/);
    await expect(chat).toBeVisible();
  });
});

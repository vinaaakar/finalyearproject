// India-only stores in the browser, both storefronts, with the configuration used for the demo: the ACADEMIC
// DEMONSTRATION INR price list (config/pricing, copied into the *_test databases by globalSetup) and the demonstration
// all-India shipping (config/shipping). No US form, no dollar amount anywhere in the customer journey.
const fs = require('fs');
const path = require('path');
const { test } = require('@playwright/test');
const h = require('./support/helpers.cjs');
const { run: prices } = require('./support/prices-setup.cjs');

const { expect } = h;
const ROOT = path.resolve(__dirname, '..', '..');
const LIST = JSON.parse(fs.readFileSync(path.join(ROOT, 'config/pricing/demo-inr-prices.json'), 'utf8'));
const SHIP = Object.fromEntries(['store-a', 'store-b'].map((s) =>
  [s, JSON.parse(fs.readFileSync(path.join(ROOT, `config/shipping/${s}.json`), 'utf8')).IN[0]]));
const inr = (paise) => `₹${new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2 }).format(paise / 100)}`;
const UNPRICED = { 'store-a': 'granite-hiking-boots', 'store-b': 'stoneware-mug-set' };

async function readyCustomer(page, request, store, label, slug = h.STORES[store].product) {
  const auth = await h.createCustomer(request, store, label);
  await h.setCartQuantity(request, store, auth, slug, 1);
  await h.signIn(page, store, auth);
  return auth;
}

test('Indian customer: Tamil Nadu, Cumbum, PIN 625521 → order in ₹ with the demonstration shipping', async ({ page, request }, info) => {
  const store = info.project.name;
  const s = h.STORES[store];
  const auth = await readyCustomer(page, request, store, 'india');
  await page.goto('/checkout');
  await expect(page.getByTestId('ship-country')).toHaveText('Delivering to India');
  await expect(page.getByLabel('Country / Region')).toHaveCount(0);                // India only: no country choice
  const states = await page.getByLabel('State / union territory').locator('option').allInnerTexts();
  expect(states.length).toBe(37);                                                // 36 + "Select…"
  expect(states).toEqual(expect.arrayContaining(['Tamil Nadu', 'Puducherry', 'Delhi', 'Ladakh']));
  expect(states).not.toContain('Alabama');
  const pin = page.getByLabel('PIN code');
  await expect(pin).toHaveAttribute('maxlength', '6');
  for (const [value, ok] of [['62552', false], ['025521', false], ['625521', true]]) {
    await pin.fill(value);
    expect(await pin.evaluate((el) => el.checkValidity()), value).toBe(ok);
  }
  const cumbum = { ...s.address, line1: '12 Kambam Main Road', city: 'Cumbum', region: 'TN', postal_code: '625521', phone: '98765 43210' };
  await h.fillIndianAddress(page, cumbum);
  expect(await page.locator('form').evaluate((f) => f.checkValidity())).toBe(true);
  // Shipping: the browser shows exactly what the server calculates from config/shipping (same amount, same rule).
  const item = LIST[store][s.product];
  const fee = item >= SHIP[store].free_over_cents ? 0 : SHIP[store].standard_cents;
  const quote = await h.api(request, store, 'POST', '/checkout/quote', { token: auth.token, body: { shipping_method: 'standard',
    destination: { country: 'IN', region: 'TN', postal_code: '625521' } } });
  expect(quote.cart.shipping_cents).toBe(fee);
  await expect(page.getByText(`Standard delivery — ${fee === 0 ? 'Free' : inr(fee)}`)).toBeVisible();
  const aside = page.locator('.cart-aside');
  await expect(aside).toContainText(inr(item));
  await expect(aside).toContainText(inr(item + fee));
  const main = page.locator('main');
  await expect(main).not.toContainText('$');
  await expect(main).not.toContainText(/Expedited|United States|ZIP/);
  await page.getByRole('button', { name: 'Review order' }).click();
  await expect(page.getByText(/Cumbum, Tamil Nadu 625521, India/)).toBeVisible();
  await expect(page.getByText('Prices in Indian rupees (₹).')).toBeVisible();
  await page.getByRole('button', { name: 'Edit shipping' }).click();                 // editing keeps everything
  await expect(page.getByLabel('City / Town')).toHaveValue('Cumbum');
  await expect(page.getByLabel('PIN code')).toHaveValue('625521');
  await page.getByRole('button', { name: 'Review order' }).click();
  await page.getByRole('button', { name: `Place order · ${inr(item + fee)}` }).click();
  await expect(page).toHaveURL(/\/orders\/[A-Z]{2}-\d{5}\/pay$/);
  const number = page.url().match(/[A-Z]{2}-\d{5}/)[0];
  try {
    await expect(main).not.toContainText('$');                                    // payment page
    await page.goto(`/orders/${number}`);
    const delivery = page.getByRole('region', { name: 'Delivery' });
    await expect(delivery).toContainText('Cumbum, TN 625521');
    await expect(delivery).toContainText('India');
    await expect(delivery).toContainText('+919876543210');
    await expect(page.getByRole('region', { name: 'Items' })).toContainText(inr(item + fee));
    await expect(main).not.toContainText('$');
  } finally {
    await h.cancelOrder(request, store, auth, number);
  }
});

test('catalogue, product and cart pages show the approved ₹ prices and never a dollar amount', async ({ page, request }, info) => {
  const store = info.project.name;
  const s = h.STORES[store];
  await readyCustomer(page, request, store, 'prices');
  await page.goto('/');
  const cards = page.locator('.product-card');
  await expect(cards.first()).toBeVisible();
  for (const card of await cards.all()) {
    const slug = (await card.getByRole('link').first().getAttribute('href')).split('/').pop();
    await expect(card.locator('.price')).toHaveText(inr(LIST[store][slug]));
  }
  await expect(page.locator('main')).not.toContainText('$');
  await page.goto(`/products/${s.product}`);
  await expect(page.locator('.detail-price')).toHaveText(inr(LIST[store][s.product]));
  await page.goto('/cart');
  await expect(page.locator('.cart-lines')).toContainText(inr(LIST[store][s.product]));
  await expect(page.locator('.cart-aside')).toContainText('Calculated at checkout');
  await expect(page.locator('main')).not.toContainText('$');
  await page.goto('/shipping');
  await expect(page.locator('main')).toContainText('Demonstration');
  await expect(page.locator('main')).toContainText(inr(SHIP[store].standard_cents));
  await expect(page.locator('main')).not.toContainText(/\$|contiguous US/);
  await expect(page.locator('footer')).not.toContainText('$');
});

test('a product without an approved ₹ price says so and can’t be ordered', async ({ page, request }, info) => {
  const store = info.project.name;
  prices('--unset', `${store}:${UNPRICED[store]}`);
  try {
    await readyCustomer(page, request, store, 'unpriced', UNPRICED[store]);
    await page.goto(`/products/${UNPRICED[store]}`);
    await expect(page.locator('.detail-price')).toHaveText('Price in ₹ not set yet');
    await page.goto('/cart');
    await expect(page.getByRole('status').filter({ hasText: 'Prices in Indian rupees' })).toContainText('never converted');
    await expect(page.getByRole('button', { name: 'Checkout', exact: true })).toBeDisabled();
    await expect(page.locator('main')).not.toContainText('$');
  } finally {
    prices();                                                                     // restore the full demonstration list
  }
});

test('the assistant quotes the same ₹ price as the product page, in its reply and its product card', async ({ page }, info) => {
  const store = info.project.name;
  const s = h.STORES[store];
  await page.goto('/');
  await page.getByRole('button', { name: `Open chat with ${s.assistant}` }).click();
  const chat = page.getByRole('dialog');
  await chat.getByRole('textbox').fill(`What is the price of the ${s.productName}?`);
  await chat.getByRole('textbox').press('Enter');
  const reply = chat.locator('.bubble-assistant').last();
  await expect(reply).toContainText(inr(LIST[store][s.product]));
  await expect(chat.locator('.product-card-compact').first()).toContainText(inr(LIST[store][s.product]));
  await expect(chat).not.toContainText('$');
});

test('India checkout form fits a phone screen', async ({ page, request }, info) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await readyCustomer(page, request, info.project.name, 'indiaphone');
  await page.goto('/checkout');
  await h.fillIndianAddress(page, h.STORES[info.project.name].address);
  expect(await h.layoutProblems(page)).toEqual([]);
});

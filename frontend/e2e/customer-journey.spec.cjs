// One customer journey, run for each storefront (project) against the isolated stack in playwright.config.js:
// browse + search → product → add to cart → register (cart is merged) → checkout → sandbox payment page →
// cancel with confirmation (stock is released again) → ask the store's assistant.
// Every account is new and synthetic (`e2e-…@example.com`); nothing touches the development databases.
const { expect, test } = require('@playwright/test');
const { fillIndianAddress } = require('./support/helpers.cjs');

const STORES = {
  'store-a': {
    name: 'Summit Trail Co.', assistant: 'Scout', search: 'backpack', product: 'Daytrip 22L Daypack', prefix: 'SA',
    address: { line1: '12 Kambam Main Road', city: 'Cumbum', region: 'TN', postal_code: '625521', phone: '98765 43210' }, returnWindow: '60',
  },
  'store-b': {
    name: 'Bloom & Brew', assistant: 'Maple', search: 'kettle', product: 'Gooseneck Pour-Over Kettle', prefix: 'BB',
    address: { line1: '45 MG Road', city: 'Bengaluru', region: 'KA', postal_code: '560001', phone: '91234 56789' }, returnWindow: '30',
  },
};

test('customer journey: search, cart, register, checkout, cancel, ask the assistant', async ({ page }, testInfo) => {
  const s = STORES[testInfo.project.name];
  const pageErrors = [];
  page.on('pageerror', (e) => pageErrors.push(e.message));

  // 1. Home and search (an everyday word must find the product)
  await page.goto('/');
  await expect(page).toHaveTitle(s.name);
  await page.getByLabel('Search products').fill(s.search);
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Search results' })).toBeVisible();
  await page.getByRole('link', { name: s.product, exact: true }).first().click();

  // 2. Product page → add to cart
  await expect(page.getByRole('heading', { level: 1, name: s.product })).toBeVisible();
  await page.getByRole('button', { name: 'Add to cart', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Cart, 1 item' })).toBeVisible();

  // 3. Register a new synthetic customer, straight back to checkout with the cart merged
  const email = `e2e-${testInfo.project.name}-${Date.now()}@example.com`;
  await page.goto('/register?next=/checkout');
  await page.getByLabel('Full name').fill('E2E Shopper');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill('E2e-Strong-Pass-42');
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page).toHaveURL(/\/checkout$/);
  await expect(page.getByRole('heading', { name: 'Checkout' })).toBeVisible();

  // 4. Indian shipping address → review → place order (prices in ₹ only)
  await fillIndianAddress(page, s.address);
  await expect(page.locator('main')).not.toContainText('$');
  await page.getByRole('button', { name: 'Review order' }).click();
  await expect(page.getByRole('heading', { name: 'Review your order' })).toBeVisible();
  await expect(page.getByText(`1 × ${s.product}`)).toBeVisible();
  await page.getByRole('button', { name: /^Place order · ₹/ }).click();

  // 5. Payment page (sandbox, clearly labelled)
  await expect(page).toHaveURL(new RegExp(`/orders/${s.prefix}-\\d{5}/pay$`));
  await expect(page.getByRole('heading', { name: 'Payment' })).toBeVisible();
  await expect(page.getByRole('note')).toContainText('TEST MODE');
  const orderNumber = page.url().match(new RegExp(`${s.prefix}-\\d{5}`))[0];

  // 6. Cancel — only after explicit confirmation; success only when the server confirms
  await page.getByRole('button', { name: 'Cancel this order' }).click();
  await expect(page.getByRole('group', { name: `Confirm cancelling order ${orderNumber}` })).toContainText('This can’t be undone.');
  await page.getByRole('button', { name: `Yes, cancel order ${orderNumber}` }).click();
  await expect(page.getByRole('heading', { name: 'Order cancelled' })).toBeVisible();
  await expect(page.getByText(`Order ${orderNumber} has been cancelled. No payment was taken.`)).toBeVisible();

  // 7. Ask the store's own assistant (opens in Tamil; replies in the language of the question)
  await page.getByRole('button', { name: `Open chat with ${s.assistant}` }).click();
  const chat = page.getByRole('dialog', { name: s.assistant });
  await expect(chat).toHaveAttribute('lang', 'ta-IN');
  await chat.getByRole('textbox').fill('What is your return policy?');
  await chat.getByRole('textbox').press('Enter');
  await expect(chat.locator('.bubble-assistant').last()).toContainText(`${s.returnWindow} days`);
  await expect(chat.getByTestId('conversation-language')).toHaveValue('en');

  expect(pageErrors, 'no uncaught page errors').toEqual([]);
});

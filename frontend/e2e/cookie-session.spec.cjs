// Phase J: run with AVC_E2E_AUTH_COOKIES=1 (the isolated API then issues HttpOnly cookie sessions). Skipped otherwise.
const { test } = require('@playwright/test');
const h = require('./support/helpers.cjs');

const { expect } = h;

test('cookie sessions: no token in the page, HttpOnly cookie, CSRF on writes', async ({ page, context }, info) => {
  test.skip(process.env.AVC_E2E_AUTH_COOKIES !== '1', 'cookie-session run only (AVC_E2E_AUTH_COOKIES=1)');
  const store = info.project.name;
  const s = h.STORES[store];
  await page.goto(`/products/${s.product}`);
  await page.getByRole('button', { name: 'Add to cart', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Cart, 1 item' })).toBeVisible();   // the guest add finished
  await page.goto('/register?next=/checkout');
  await page.getByLabel('Full name').fill('Cookie Shopper');
  await page.getByLabel('Email').fill(`e2e-cookie-${store}-${Date.now()}@example.com`);
  await page.getByLabel('Password').fill('E2e-Strong-Pass-42');
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page.getByRole('heading', { name: 'Checkout' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Cart, 1 item' })).toBeVisible();     // guest cart merged into the account (CSRF-protected POST)

  const stored = await page.evaluate((k) => JSON.parse(sessionStorage.getItem(k)), `avc:${store}:session`);
  expect(stored.cookie).toBe(true);
  expect(stored.token).toBeUndefined();                                      // nothing a page script could steal
  expect(await page.evaluate(() => document.cookie)).not.toContain('avc_session');
  const cookies = await context.cookies();
  const session = cookies.find((c) => c.name === `avc_session_${store.replace('-', '_')}`);
  expect(session).toMatchObject({ httpOnly: true, sameSite: 'Strict', path: `/api/stores/${store}` });

  // A write without the CSRF header is refused even though the browser sends the cookie
  const forged = await page.evaluate(async (st) => (await fetch(`/api/stores/${st}/cart/items/x-y`, { method: 'PUT',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ quantity: 1 }) })).status, store);
  expect(forged).toBe(403);
});

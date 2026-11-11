// Phase E end-to-end: a customer finds an order from their account and opens its details; the support pages show
// the store's own verified information; another customer cannot open that order.
const { test } = require('@playwright/test');
const h = require('./support/helpers.cjs');

const { expect } = h;

test('order details from the account, and isolation between customers', async ({ page, request, browser }, info) => {
  const store = info.project.name;
  const s = h.STORES[store];
  const auth = await h.createCustomer(request, store, 'orders');
  const number = await h.placeOrder(request, store, auth);
  try {
    await h.signIn(page, store, auth);
    await page.goto('/account');
    await page.getByRole('link', { name: `View details of order ${number}` }).click();
    await expect(page).toHaveURL(new RegExp(`/orders/${number}$`));
    await expect(page.getByRole('heading', { level: 1, name: `Order ${number}` })).toBeVisible();
    const items = page.getByRole('region', { name: 'Items' });
    await expect(items.getByRole('link', { name: s.productName })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Delivery' })).toContainText(s.address.line1);
    await expect(page.getByRole('link', { name: 'Pay now' })).toHaveAttribute('href', `/orders/${number}/pay`);

    // Another customer of the same store sees "not found" (same as a non-existent order)
    const other = await h.createCustomer(request, store, 'other');
    const ctx = await browser.newContext({ baseURL: info.project.use.baseURL });
    const page2 = await ctx.newPage();
    await h.signIn(page2, store, other);
    await page2.goto(`/orders/${number}`);
    await expect(page2.getByRole('heading', { name: 'Order not found' })).toBeVisible();
    await expect(page2.getByText(s.address.line1)).toHaveCount(0);
    await ctx.close();
  } finally {
    await h.cancelOrder(request, store, auth, number);
  }
});

test('support pages show the store\'s own information', async ({ page }, info) => {
  const s = h.STORES[info.project.name];
  await page.goto('/');
  await page.getByRole('navigation', { name: 'Customer service' }).getByRole('link', { name: 'Help' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Help' })).toBeVisible();
  await page.getByRole('link', { name: 'Returns and warranty' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Returns' })).toBeVisible();
  await expect(page.locator('main')).not.toContainText(/prepaid label|store credit|PayPal|gift card/i);
  await page.goto('/contact');
  await expect(page.getByText(/hasn’t published a postal address, phone number or tax registration/)).toBeVisible();
  await page.getByRole('button', { name: `Ask ${s.assistant}` }).click();
  await expect(page.getByRole('dialog', { name: s.assistant })).toBeVisible();
});

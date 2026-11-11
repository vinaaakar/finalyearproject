// Phase F end-to-end: a paid order is shipped, put out for delivery and delivered by staff in the browser; the customer
// sees the tracking and status history; customers cannot reach the staff screens.
const { test } = require('@playwright/test');
const h = require('./support/helpers.cjs');

const { expect } = h;

test('staff fulfil a paid order and the customer sees tracking and history', async ({ page, request, browser }, info) => {
  const store = info.project.name;
  const s = h.STORES[store];
  const customer = await h.createCustomer(request, store, 'fulfil');
  const number = await h.placeOrder(request, store, customer);
  await h.payOrder(request, store, customer, number);

  const staff = await h.staffLogin(request, store);
  await h.signIn(page, store, staff);
  await page.goto('/account');
  await page.getByRole('link', { name: 'Fulfil orders' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Fulfil orders' })).toBeVisible();
  await page.getByLabel('Search by order number or customer name').fill(number);
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await page.getByRole('link', { name: number }).click();
  await expect(page.getByRole('heading', { level: 1, name: `Order ${number}` })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Items' })).toContainText(s.productName);

  await page.getByLabel('Carrier').fill('Blue Dart');
  await page.getByLabel('Tracking number').fill('BD9876543210');
  await page.getByLabel(/Tracking link/).fill('https://track.example.org/BD9876543210');
  await page.getByLabel(/Note for the order history/).fill('packed with care');
  await page.getByRole('button', { name: 'Mark as shipped' }).click();
  await expect(page.getByRole('status').filter({ hasText: `Order ${number} is now shipped.` })).toBeVisible();
  await page.getByRole('button', { name: 'Mark out for delivery' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'out for delivery' })).toBeVisible();
  await page.getByRole('button', { name: 'Mark as delivered' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'delivered' })).toBeVisible();
  const history = page.getByRole('region', { name: 'History' });
  await expect(history).toContainText('packed with care');
  await expect(history).toContainText('(staff)');

  // The customer's view
  const ctx = await browser.newContext({ baseURL: info.project.use.baseURL });
  const cpage = await ctx.newPage();
  await h.signIn(cpage, store, customer);
  await cpage.goto(`/orders/${number}`);
  await expect(cpage.getByRole('link', { name: /Track BD9876543210/ })).toHaveAttribute('href', 'https://track.example.org/BD9876543210');
  const updates = cpage.getByRole('region', { name: 'Status updates' });
  await expect(updates.getByRole('listitem')).toHaveCount(5);
  await expect(updates).not.toContainText('packed with care');   // staff notes stay internal
  await expect(cpage.getByRole('list', { name: 'Order progress' }).getByText('Delivered').locator('xpath=..')).toHaveAttribute('aria-current', 'step');

  // A customer cannot use the staff screens
  await cpage.goto('/staff/orders');
  await expect(cpage.getByRole('heading', { name: 'Staff only' })).toBeVisible();
  await ctx.close();
});

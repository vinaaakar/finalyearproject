// Customer-care workflows in the browser, both storefronts (India configuration, isolated stack): a customer reports a
// problem on a delivered order, staff assign / message / resolve it, and the customer sees the update; the assistant
// registers a request by conversation only after an explicit confirmation; return eligibility and simulated refunds;
// phone layout and accessibility of the new screens. Synthetic accounts and orders only (*_test databases).
const { test } = require('@playwright/test');
const h = require('./support/helpers.cjs');

const { expect } = h;

async function deliveredOrder(request, store) {
  const auth = await h.createCustomer(request, store, 'care');
  const number = await h.placeOrder(request, store, auth);
  await h.payOrder(request, store, auth, number);
  const staff = await h.staffLogin(request, store);
  await h.api(request, store, 'POST', `/staff/orders/${number}/ship`, { token: staff.token,
    body: { expected_status: 'processing', carrier: 'DemoPost', tracking_number: 'TRK98765' } });
  await h.api(request, store, 'POST', `/staff/orders/${number}/deliver`, { token: staff.token, body: { expected_status: 'shipped' } });
  return { auth, number, staff };
}

test('complaint from the order page → staff assign, message and resolve → the customer sees it', async ({ page, browser, request }, info) => {
  const store = info.project.name;
  const s = h.STORES[store];
  const { auth, number, staff } = await deliveredOrder(request, store);
  await h.signIn(page, store, auth);
  await page.goto(`/orders/${number}`);
  await page.getByRole('navigation', { name: 'Help with this order' }).getByRole('link', { name: 'Report a problem' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Report a problem' })).toBeVisible();
  await expect(page.getByLabel('Order (optional)')).toHaveValue(number);
  await page.getByLabel('Reason').selectOption('damaged');
  await page.getByLabel('Describe it in your own words').fill('The box was crushed and the item is cracked.');
  await page.getByRole('button', { name: 'Review' }).click();
  await expect(page.getByRole('heading', { name: 'Check before sending' })).toBeVisible();
  await page.getByRole('button', { name: 'Confirm and send' }).click();
  await expect(page).toHaveURL(/\/support\/requests\/(SA|BB)-CMP-\d{5}$/);
  const ref = page.url().split('/').pop();
  await expect(page.getByRole('heading', { level: 1, name: ref })).toBeVisible();
  await expect(page.locator('.care-status').first()).toHaveText('Open');

  // Staff, in their own browser context, on the same store's dashboard
  const ctx = await browser.newContext({ baseURL: info.project.use.baseURL });
  const staffPage = await ctx.newPage();
  await h.signIn(staffPage, store, staff);
  await staffPage.goto('/staff/care');
  await expect(staffPage.getByRole('heading', { name: 'Customer care' })).toBeVisible();
  await staffPage.getByRole('link', { name: ref }).click();
  await expect(staffPage.getByRole('heading', { level: 1, name: ref })).toBeVisible();
  await staffPage.getByLabel('Assign to').selectOption({ index: 1 });
  await staffPage.getByRole('button', { name: 'Assign' }).click();
  await expect(staffPage.locator('main').getByRole('status')).toHaveText('Assigned.');
  await staffPage.getByLabel('Internal note (never shown to the customer)').fill('INTERNAL: checked the courier photos');
  await staffPage.getByRole('button', { name: 'Add note' }).click();
  await expect(staffPage.locator('main').getByRole('status')).toHaveText('Internal note added.');
  await staffPage.getByRole('radio', { name: 'Start review' }).check();
  await staffPage.getByRole('button', { name: 'Save' }).click();
  await expect(staffPage.locator('main').getByRole('status')).toHaveText('Status updated.');
  await staffPage.getByRole('radio', { name: 'Mark resolved' }).check();
  await staffPage.getByLabel(/Message to the customer \(optional\)/).fill('A replacement is on its way (demo).');
  await staffPage.getByRole('button', { name: 'Save' }).click();
  await expect(staffPage.locator('.care-status').first()).toHaveText('Resolved');
  await ctx.close();

  // The customer sees the decision and the team's message — never the internal note
  await page.reload();
  await expect(page.locator('.care-status').first()).toHaveText('Resolved');
  await expect(page.getByText('A replacement is on its way (demo).')).toBeVisible();
  await expect(page.locator('main')).not.toContainText('INTERNAL');
  await expect(page.locator('main')).not.toContainText('$');
  await expect(page.getByLabel('Send a message to the store team')).toHaveCount(0);        // closed requests take no replies
  await page.goto('/support/requests');
  await expect(page.getByRole('link', { name: ref })).toBeVisible();
  void s;
});

test('the assistant registers a complaint only after Confirm, and reads back the server’s reference', async ({ page, request }, info) => {
  const store = info.project.name;
  const s = h.STORES[store];
  const { auth, number } = await deliveredOrder(request, store);
  await h.signIn(page, store, auth);
  await page.goto('/');
  await page.getByRole('button', { name: `Open chat with ${s.assistant}` }).click();
  const chat = page.getByRole('dialog');
  const say = async (text) => {
    await chat.getByRole('textbox').fill(text);
    await chat.getByRole('textbox').press('Enter');
  };
  await say('I received a damaged product.');
  await chat.getByRole('button', { name: number }).click();                                 // choose the order
  await expect(chat.locator('.bubble-assistant').last()).toContainText('describe');
  await say('The lid is cracked and it leaks.');
  await expect(chat.locator('.bubble-assistant').last()).toContainText('Please check before I submit');
  const before = await h.api(request, store, 'GET', '/care/requests', { token: auth.token });
  expect(before.requests).toEqual([]);                                                     // nothing until confirmed
  await chat.getByRole('button', { name: 'Confirm and submit' }).click();
  const after = await expect.poll(async () => (await h.api(request, store, 'GET', '/care/requests', { token: auth.token })).requests.length).toBe(1);
  void after;
  const mine = (await h.api(request, store, 'GET', '/care/requests', { token: auth.token })).requests[0];
  await expect(chat.locator('.bubble-assistant').last()).toContainText(`Your complaint reference is ${mine.reference}`);
  await chat.getByRole('button', { name: `View ${mine.reference}` }).click();
  await expect(page.getByRole('heading', { level: 1, name: mine.reference })).toBeVisible();
});

test('returns follow the store’s policy window; refund requests are simulated and need staff to complete', async ({ page, request }, info) => {
  const store = info.project.name;
  const { auth, number, staff } = await deliveredOrder(request, store);
  await h.signIn(page, store, auth);
  await page.goto(`/support/new?kind=return&order=${number}`);
  await expect(page.getByText(/-day returns policy, a return can be requested until/)).toBeVisible();
  await page.goto(`/support/new?kind=refund&order=${number}`);
  await expect(page.getByRole('note')).toContainText('no real money is transferred');
  await page.getByLabel('Reason').selectOption('damaged');
  await page.getByLabel('Describe it in your own words').fill('Arrived broken.');
  await page.getByRole('button', { name: 'Review' }).click();
  await page.getByRole('button', { name: 'Confirm and send' }).click();
  await expect(page).toHaveURL(/RFD-\d{5}$/);
  const ref = page.url().split('/').pop();
  for (const [from, to] of [['requested', 'under_review'], ['under_review', 'approved'], ['approved', 'simulated_completed']]) {
    await h.api(request, store, 'POST', `/staff/care/${ref}/status`, { token: staff.token, body: { status: to, expected_status: from } });
  }
  await page.reload();
  await expect(page.locator('.care-status').first()).toContainText('simulated — no money moved');
  await expect(page.getByRole('note')).toContainText('no real money is transferred');
});

test('customer-care screens fit a phone and pass the accessibility scan', async ({ page, request }, info) => {
  const store = info.project.name;
  const { auth, number, staff } = await deliveredOrder(request, store);
  await page.setViewportSize({ width: 375, height: 812 });
  await h.signIn(page, store, auth);
  await page.goto(`/support/new?kind=complaint&order=${number}`);
  await expect(page.getByLabel('Reason')).toBeVisible();
  expect(await h.layoutProblems(page)).toEqual([]);
  const r1 = await h.axeScan(page, info, { store, view: 'care-new@phone', baselineView: 'care-new', size: 'phone' });
  expect(r1.unexpected.map((v) => `${v.rule}: ${v.target}`)).toEqual([]);
  const created = await h.api(request, store, 'POST', '/care/requests', { token: auth.token, headers: { 'Idempotency-Key': `e2e_care_${Date.now()}_x` },
    body: { kind: 'escalation', category: 'order_problem', description: 'Please check my order.', order_number: number } });
  await page.goto(`/support/requests/${created.request.reference}`);
  await expect(page.getByRole('heading', { level: 1, name: created.request.reference })).toBeVisible();
  expect(await h.layoutProblems(page)).toEqual([]);
  const r2 = await h.axeScan(page, info, { store, view: 'care-request@phone', baselineView: 'care-request', size: 'phone' });
  expect(r2.unexpected.map((v) => `${v.rule}: ${v.target}`)).toEqual([]);
  await h.signIn(page, store, staff);
  await page.goto(`/staff/care/${created.request.reference}`);
  await expect(page.getByRole('heading', { level: 1, name: created.request.reference })).toBeVisible();
  expect(await h.layoutProblems(page)).toEqual([]);
  const r3 = await h.axeScan(page, info, { store, view: 'staff-care@phone', baselineView: 'staff-care', size: 'phone' });
  expect(r3.unexpected.map((v) => `${v.rule}: ${v.target}`)).toEqual([]);
});

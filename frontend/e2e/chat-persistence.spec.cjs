// The chat survives a page refresh in the real browser (both storefronts, isolated stack, synthetic accounts): the
// conversation and an unfinished customer-care request are restored from sessionStorage, the request can be finished
// after the reload, and signing out removes the conversation.
const { test } = require('@playwright/test');
const h = require('./support/helpers.cjs');

const { expect } = h;

test('refresh keeps the conversation and the care request; sign-out clears it', async ({ page, request }, info) => {
  const store = info.project.name;
  const s = h.STORES[store];
  const auth = await h.createCustomer(request, store, 'persist');
  const number = await h.placeOrder(request, store, auth);
  await h.payOrder(request, store, auth, number);
  await h.signIn(page, store, auth);
  await page.goto('/');
  await page.getByRole('button', { name: `Open chat with ${s.assistant}` }).click();
  let chat = page.getByRole('dialog');
  await chat.getByRole('textbox').fill('I received a damaged product.');
  await chat.getByRole('textbox').press('Enter');
  await expect(chat.getByRole('button', { name: number })).toBeVisible();               // the draft asks which order

  await page.reload();
  await page.getByRole('button', { name: `Open chat with ${s.assistant}` }).click();
  chat = page.getByRole('dialog');
  await expect(chat.getByText('I received a damaged product.')).toBeVisible();          // restored after the refresh
  await chat.getByRole('textbox').fill(number);                                          // the draft continues
  await chat.getByRole('textbox').press('Enter');
  await expect(chat.locator('.bubble-assistant').last()).toContainText('describe');

  const stored = await page.evaluate((id) => Object.keys(sessionStorage).filter((k) => k.startsWith(`avc:${id}:chat:`)), store);
  expect(stored).toHaveLength(1);
  expect(stored[0]).not.toContain('@');                                                 // no e-mail address in the key

  expect((await h.api(request, store, 'GET', '/care/requests', { token: auth.token })).requests).toEqual([]);   // nothing submitted

  await page.goto('/account');
  await page.getByRole('button', { name: 'Sign out' }).click();
  await page.getByRole('button', { name: `Open chat with ${s.assistant}` }).click();
  await expect(page.getByRole('dialog').getByText('I received a damaged product.')).toHaveCount(0);
  expect(await page.evaluate((key) => sessionStorage.getItem(key), stored[0])).toBeNull();
});

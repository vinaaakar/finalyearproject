// Phase I: the storefront interface switches between English, Tamil and Hindi, remembers the choice, sets the page
// language for assistive technology, and loads the store's own translated policies.
const { test } = require('@playwright/test');
const h = require('./support/helpers.cjs');

const { expect } = h;

test('interface language: Tamil and Hindi navigation, policies and page language', async ({ page }, info) => {
  const s = h.STORES[info.project.name];
  await page.goto('/returns');
  await expect(page.getByRole('heading', { level: 1, name: 'Returns' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');

  await page.getByTestId('ui-language').selectOption('ta');
  await expect(page.locator('html')).toHaveAttribute('lang', 'ta-IN');
  await expect(page.getByRole('heading', { level: 1, name: 'திருப்பி அனுப்புதல்' })).toBeVisible();
  const nav = page.getByRole('navigation', { name: 'முதன்மை' });
  await expect(nav.getByRole('link', { name: 'கடை' })).toBeVisible();
  await expect(page.locator('main .support-lead')).toContainText(/[஀-௿]/);     // the store's Tamil policy text
  await expect(page.getByRole('button', { name: `${s.assistant}-இடம் கேளுங்கள்` })).toBeVisible();

  await page.reload();                                                                   // remembered
  await expect(page.locator('html')).toHaveAttribute('lang', 'ta-IN');
  await expect(page.getByTestId('ui-language')).toHaveValue('ta');

  await page.getByTestId('ui-language').selectOption('hi');
  await page.goto('/contact');
  await expect(page.getByRole('heading', { level: 1, name: 'संपर्क करें' })).toBeVisible();
  await expect(page.getByText(/डाक पता, फ़ोन नंबर या टैक्स पंजीकरण/)).toBeVisible();

  const r = await h.axeScan(page, info, { store: info.project.name, view: 'support-contact-hi@desktop', baselineView: 'support-contact-hi' });
  expect(r.unexpected.map((v) => `${v.rule}: ${v.target}`)).toEqual([]);

  await page.getByTestId('ui-language').selectOption('en');
  await expect(page.getByRole('heading', { level: 1, name: 'Contact us' })).toBeVisible();
});

test('a phone layout fits in Tamil (longer words)', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/help');
  await page.getByTestId('ui-language').selectOption('ta');
  await expect(page.getByRole('heading', { level: 1, name: 'உதவி' })).toBeVisible();
  await page.waitForLoadState('networkidle');
  expect(await h.layoutProblems(page)).toEqual([]);
});

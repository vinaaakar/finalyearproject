import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CheckoutPage from '../pages/CheckoutPage.jsx';
import { apiError, deferred, makeApi, makeStore, renderAt } from './helpers.jsx';

const store = vi.hoisted(() => ({ value: null }));
vi.mock('../StoreApp.jsx', () => ({ useStore: () => store.value }));

const QUOTE = {
  items: [{ slug: 'lumen-300-headlamp', name: 'Lumen 300 Headlamp', quantity: 1, line_total: '$39.00', unit_price: '$39.00' }],
  shipping_options: [{ method: 'standard', label: 'Standard', cents: 695, price: '$6.95' },
                     { method: 'expedited', label: 'Expedited (2-day)', cents: 1495, price: '$14.95' }],
  shipping_method: 'standard', shipping_cents: 695, shipping: '$6.95', subtotal: '$39.00', total: '$45.95', total_cents: 4595,
  problems: [], can_checkout: true, currency: 'USD', prices_available: true,
};

// Default: a store whose checkout offers only the United States (the US tests below); country tests pass both.
function setup({ quote = QUOTE, session, storeId = 'store-a', api = {}, deliveryCountry = null } = {}) {
  const a = makeApi({ quote: vi.fn().mockResolvedValue(quote),
    addressOptions: vi.fn().mockResolvedValue({ countries: [USA], default_country: 'US' }), ...api });
  store.value = makeStore({ storeId, api: a, deliveryCountry, ...(session !== undefined ? { session } : {}) });
  renderAt(<CheckoutPage />, { path: '/checkout', route: '/checkout' });
  return a;
}

async function fillAddress(user, { zip = '80302', region = 'CO' } = {}) {
  await user.type(await screen.findByLabelText('Full name'), ' Jr');
  await user.type(screen.getByLabelText('Address'), '1 Trail Way');
  await user.type(screen.getByLabelText('City'), 'Boulder');
  await user.selectOptions(screen.getByLabelText('State'), region);
  await user.type(screen.getByLabelText('ZIP code'), zip);
}

describe('CheckoutPage gates', () => {
  it('asks a signed-out shopper to sign in and keeps the cart', () => {
    const api = setup({ session: null });
    expect(screen.getByText('Please sign in to check out. Your cart is kept.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/account?next=/checkout');
    expect(screen.getByRole('link', { name: 'Create an account' })).toHaveAttribute('href', '/register?next=/checkout');
    expect(api.quote).not.toHaveBeenCalled();
  });

  it('refuses staff accounts', () => {
    setup({ session: { customer: { name: 'Agent', role: 'agent' } } });
    expect(screen.getByText('Staff accounts can’t place orders.')).toBeInTheDocument();
  });

  it('shows an empty-cart state', async () => {
    setup({ quote: { ...QUOTE, items: [] } });
    expect(await screen.findByText('Your cart is empty.')).toBeInTheDocument();
  });

  it('shows the server error when the quote cannot be loaded', async () => {
    setup({ api: { quote: vi.fn().mockRejectedValue(apiError('Cannot reach the server. Please check that the backend is running.', 0, 'network')) } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the server');
  });
});

describe('CheckoutPage validation', () => {
  it('marks every required field and validates the ZIP format', async () => {
    setup();
    for (const label of ['Full name', 'Address', 'City', 'State', 'ZIP code']) {
      expect(await screen.findByLabelText(label)).toBeRequired();
    }
    expect(screen.getByLabelText(/Apartment, suite/)).not.toBeRequired();
    const zip = screen.getByLabelText('ZIP code');
    const user = userEvent.setup();
    await user.type(zip, '8030');
    expect(zip).not.toBeValid();
    await user.clear(zip);
    await user.type(zip, '80302-1234');
    expect(zip).toBeValid();
  });

  it('cannot reach review while required fields are empty', async () => {
    setup();
    const form = (await screen.findByRole('button', { name: 'Review order' })).closest('form');
    expect(form.checkValidity()).toBe(false);
  });

  it('disables review when the cart has a stock problem', async () => {
    setup({ quote: { ...QUOTE, can_checkout: false, problems: ['Only 1 of Lumen 300 Headlamp left.'] } });
    expect(await screen.findByRole('button', { name: 'Review order' })).toBeDisabled();
  });

  it('re-quotes when the shipping method changes', async () => {
    const user = userEvent.setup();
    const api = setup();
    await user.click(await screen.findByRole('radio', { name: /Expedited \(2-day\)/ }));
    await waitFor(() => expect(api.quote).toHaveBeenLastCalledWith('expedited', { country: 'US' }));
  });
});

describe.each([['store-a', 'Summit Trail Co.'], ['store-b', 'Bloom & Brew']])('CheckoutPage submission (%s)', (storeId, storeName) => {
  it('reviews the address and places the order with the reviewed total and an idempotency key', async () => {
    const user = userEvent.setup();
    const api = setup({ storeId, api: { checkout: vi.fn().mockResolvedValue({ order: { order_number: 'SA-50002' } }) } });
    await fillAddress(user);
    await user.click(screen.getByRole('button', { name: 'Review order' }));
    expect(await screen.findByRole('heading', { name: 'Review your order' })).toBeInTheDocument();
    expect(screen.getByText(/1 Trail Way/)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`${storeName.replace('&', '\\&')} payments run in sandbox test mode`))).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Place order · $45.95' }));
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/orders/SA-50002/pay'));
    const [arg] = api.checkout.mock.calls[0];
    expect(arg).toMatchObject({ shippingMethod: 'standard', expectedTotalCents: 4595,
      shipping: { full_name: 'Test Shopper Jr', line1: '1 Trail Way', line2: null, city: 'Boulder', region: 'CO', postal_code: '80302', country: 'US' } });
    expect(typeof arg.idempotencyKey).toBe('string');
    expect(arg.idempotencyKey.length).toBeGreaterThan(10);
  });
});

describe('CheckoutPage submission errors', () => {
  async function toReview(user) {
    await fillAddress(user);
    await user.click(screen.getByRole('button', { name: 'Review order' }));
    return screen.findByRole('button', { name: 'Place order · $45.95' });
  }

  it('sends one order while the first submission is in flight', async () => {
    const user = userEvent.setup();
    const pending = deferred();
    const api = setup({ api: { checkout: vi.fn(() => pending.promise) } });
    const place = await toReview(user);
    await user.dblClick(place);
    expect(await screen.findByRole('button', { name: 'Placing order…' })).toBeDisabled();
    pending.resolve({ order: { order_number: 'SA-50003' } });
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/orders/SA-50003/pay'));
    expect(api.checkout).toHaveBeenCalledTimes(1);
  });

  it('reuses the same idempotency key when retrying after a network error', async () => {
    const user = userEvent.setup();
    const checkout = vi.fn()
      .mockRejectedValueOnce(apiError('Cannot reach the server. Please check that the backend is running.', 0, 'network'))
      .mockResolvedValueOnce({ order: { order_number: 'SA-50004' } });
    setup({ api: { checkout } });
    const place = await toReview(user);
    await user.click(place);
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the server');
    await user.click(screen.getByRole('button', { name: 'Place order · $45.95' }));
    await waitFor(() => expect(checkout).toHaveBeenCalledTimes(2));
    expect(checkout.mock.calls[1][0].idempotencyKey).toBe(checkout.mock.calls[0][0].idempotencyKey);
  });

  it('shows a price change (409), refreshes the quote and uses a new key for the next attempt', async () => {
    const user = userEvent.setup();
    const checkout = vi.fn()
      .mockRejectedValueOnce(apiError('Prices or shipping changed since you reviewed your order. Please review it again.', 409, 'total_changed'))
      .mockResolvedValueOnce({ order: { order_number: 'SA-50005' } });
    const api = setup({ api: { checkout } });
    const place = await toReview(user);
    await user.click(place);
    expect(await screen.findByRole('alert')).toHaveTextContent('Prices or shipping changed');
    expect(screen.getByRole('heading', { name: 'Review your order' })).toBeInTheDocument();
    await waitFor(() => expect(api.quote.mock.calls.length).toBeGreaterThanOrEqual(2));
    await user.click(screen.getByRole('button', { name: 'Place order · $45.95' }));
    await waitFor(() => expect(checkout).toHaveBeenCalledTimes(2));
    expect(checkout.mock.calls[1][0].idempotencyKey).not.toBe(checkout.mock.calls[0][0].idempotencyKey);
  });

  it('returns to the shipping step with the server validation error (422)', async () => {
    const user = userEvent.setup();
    const err = apiError('Sorry, this store does not ship to that state.', 422, 'region_not_served',
      [{ field: 'shipping.region', issue: 'not served by this store' }]);
    setup({ api: { checkout: vi.fn().mockRejectedValue(err) } });
    const place = await toReview(user);
    await user.click(place);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Sorry, this store does not ship to that state.');
    expect(alert).toHaveTextContent('region: Not served by this store.');
    expect(screen.getByRole('heading', { name: 'Shipping address' })).toBeInTheDocument();
  });
});

// Country-aware checkout: the countries and their rules come from GET /checkout/address-options (app/markets.py).
const IN_REGIONS = [['AP', 'Andhra Pradesh'], ['KL', 'Kerala'], ['TN', 'Tamil Nadu'], ['PY', 'Puducherry'], ['DL', 'Delhi']];
const INDIA = { code: 'IN', country: 'IN', name: 'India', region_label: 'State / union territory',
  regions: IN_REGIONS.map(([code, name]) => ({ code, name, kind: 'state' })), postal_label: 'PIN code', postal_pattern: '^[1-9][0-9]{5}$',
  postal_example: '625521', phone: { required: true, pattern: '^(\\+?91)?[6-9]\\d{9}$', example: '98765 43210', dial_code: '+91' },
  line1_label: 'Address line 1', line2_label: 'Address line 2 / Landmark (optional)', city_label: 'City / Town', shipping_configured: false,
  currency: 'INR', prices_configured: false };
const USA = { code: 'US', country: 'US', name: 'United States', region_label: 'State',
  regions: [['AL', 'Alabama'], ['CO', 'Colorado'], ['DC', 'District of Columbia']].map(([code, name]) => ({ code, name, kind: 'state' })),
  postal_label: 'ZIP code', postal_pattern: '^\\d{5}(-\\d{4})?$', postal_example: '80302',
  phone: { required: false, pattern: '^(\\+?1)?[2-9]\\d{9}$', example: '303 555 0100', dial_code: '+1' },
  line1_label: 'Address', line2_label: 'Apartment, suite, etc. (optional)', city_label: 'City', shipping_configured: true,
  currency: 'USD', prices_configured: true };
// India with (test) approved INR prices but no delivery rates.
const NO_RATES = { ...QUOTE, currency: 'INR', items: [{ ...QUOTE.items[0], line_total: '₹1,999.00', unit_price: '₹1,999.00' }],
  subtotal: '₹1,999.00', shipping_options: [], shipping_cents: null, shipping: null, shipping_available: false, total: '₹1,999.00',
  total_cents: 199900, total_excludes_shipping: true, can_checkout: false,
  shipping_problem: "Shipping to this address isn't available yet: the store hasn't set delivery rates for it, so the order can't be placed." };
// India today: no approved INR prices and no rates — the server sends no amounts at all.
const NO_PRICES = { ...NO_RATES, prices_available: false, items: [{ ...QUOTE.items[0], line_total: null, unit_price: null, line_total_cents: null }],
  subtotal: null, subtotal_cents: null, total: null, total_cents: null,
  price_problem: "Prices in INR haven't been set for this item yet, so an order can't be placed." };

function setupCountries({ defaultCountry = 'IN', quote = vi.fn((m, d) => Promise.resolve(d?.country === 'IN' ? NO_RATES : QUOTE)), storeId = 'store-a', checkout } = {}) {
  return setup({ storeId, api: { addressOptions: vi.fn().mockResolvedValue({ countries: [INDIA, USA], default_country: defaultCountry }), quote,
    ...(checkout ? { checkout } : {}) } });
}
const optionNames = (label) => within(screen.getByLabelText(label)).getAllByRole('option').map((o) => o.textContent);

describe.each([['store-a'], ['store-b']])('CheckoutPage country-aware address (%s)', (storeId) => {
  it('India (default for a new customer): Indian states and union territories, PIN code, +91 mobile, no US-only text', async () => {
    const user = userEvent.setup();
    setupCountries({ storeId });
    expect(await screen.findByLabelText('Country / Region')).toHaveValue('IN');
    expect(optionNames('State / union territory')).toEqual(['Select…', 'Andhra Pradesh', 'Kerala', 'Tamil Nadu', 'Puducherry', 'Delhi']);
    expect(optionNames('State / union territory')).not.toContain('Alabama');
    await user.selectOptions(screen.getByLabelText('State / union territory'), 'TN');
    expect(screen.getByLabelText('State / union territory')).toHaveValue('TN');
    const pin = screen.getByLabelText('PIN code');
    for (const [value, valid] of [['625521', true], ['62552', false], ['025521', false], ['62552a', false]]) {
      await user.clear(pin);
      await user.type(pin, value);
      expect(pin.validity.valid, value).toBe(valid);
    }
    await user.clear(pin);
    await user.type(pin, '6255211');                                       // a seventh digit can't be entered
    expect(pin).toHaveValue('625521');
    expect(screen.getByLabelText('Mobile number')).toBeRequired();
    expect(screen.getByText('Country code +91. For example 98765 43210.')).toBeInTheDocument();
    expect(screen.getByLabelText('City / Town')).toBeRequired();
    expect(screen.getByLabelText('Address line 2 / Landmark (optional)')).not.toBeRequired();
    expect(screen.queryByText('United States addresses only.')).not.toBeInTheDocument();
  });

  it('switching India → United States → India changes the fields and validation', async () => {
    const user = userEvent.setup();
    setupCountries({ storeId });
    const countrySelect = await screen.findByLabelText('Country / Region');
    await user.selectOptions(screen.getByLabelText('State / union territory'), 'TN');
    await user.type(screen.getByLabelText('PIN code'), '625521');
    await user.selectOptions(countrySelect, 'US');
    expect(optionNames('State')).toEqual(['Select…', 'Alabama', 'Colorado', 'District of Columbia']);
    expect(screen.getByLabelText('State')).toHaveValue('');                  // a Tamil Nadu choice can't carry over
    const zip = screen.getByLabelText('ZIP code');
    expect(zip).toHaveValue('');
    for (const [value, valid] of [['80302', true], ['80302-1234', true], ['8030', false], ['625521', false]]) {
      await user.clear(zip);
      await user.type(zip, value);
      expect(zip.validity.valid, value).toBe(valid);
    }
    expect(screen.getByLabelText('Phone number (optional)')).not.toBeRequired();
    await user.selectOptions(countrySelect, 'IN');
    expect(screen.getByLabelText('PIN code')).toHaveValue('');
    expect(screen.getByLabelText('Mobile number')).toBeRequired();
    expect(optionNames('State / union territory')).toContain('Tamil Nadu');
  });
});

describe('CheckoutPage country-aware shipping and review', () => {
  it('India without rates: no US prices, shipping marked for confirmation, the address survives review and editing, ordering is blocked', async () => {
    const user = userEvent.setup();
    const quote = vi.fn((m, d) => Promise.resolve(d?.country === 'IN' ? NO_RATES : QUOTE));
    const api = setupCountries({ quote });
    await screen.findByLabelText('Country / Region');
    await user.type(screen.getByLabelText('Address line 1'), '12 Kambam Main Road');
    await user.type(screen.getByLabelText('City / Town'), 'Cumbum');
    await user.selectOptions(screen.getByLabelText('State / union territory'), 'TN');
    await user.type(screen.getByLabelText('PIN code'), '625521');
    await user.type(screen.getByLabelText('Mobile number'), '98765 43210');
    await waitFor(() => expect(api.quote).toHaveBeenLastCalledWith('standard', { country: 'IN', region: 'TN', postal_code: '625521' }));
    expect(screen.getByText(/Shipping rates not configured/)).toHaveTextContent('for India (Tamil Nadu)');
    expect(screen.queryByRole('group', { name: 'Shipping method' })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/Expedited \(2-day\)|\$/);
    expect(screen.getAllByText('₹1,999.00', { selector: 'dd' })).toHaveLength(2);           // subtotal and total, in rupees
    expect(screen.getByText('To be confirmed')).toBeInTheDocument();
    expect(screen.getByText('Total (before shipping)')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Review order' }));
    const review = await screen.findByRole('heading', { name: 'Review your order' });
    const card = review.closest('.card');
    expect(within(card).getByText(/Cumbum, Tamil Nadu 625521, India/)).toBeInTheDocument();
    expect(within(card).getByText(/\+91 98765 43210/)).toBeInTheDocument();
    expect(within(card).getByRole('status')).toHaveTextContent('Shipping rates not configured');
    expect(screen.getByRole('button', { name: /^Place order/ })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Edit shipping' }));
    expect(screen.getByLabelText('City / Town')).toHaveValue('Cumbum');                  // editing keeps the address
    expect(screen.getByLabelText('PIN code')).toHaveValue('625521');
    expect(screen.getByLabelText('Country / Region')).toHaveValue('IN');
  });

  it('India with rates: places the order with country, PIN and phone', async () => {
    const user = userEvent.setup();
    const RATED = { ...NO_RATES, shipping_options: [{ method: 'standard', label: 'Standard (4–7 days)', cents: 12000, price: '₹120.00' }],
      shipping_cents: 12000, shipping: '₹120.00', total: '₹2,119.00', total_cents: 211900, shipping_available: true,
      total_excludes_shipping: false, can_checkout: true };
    const checkout = vi.fn().mockResolvedValue({ order: { order_number: 'SA-50077' } });
    const api = setupCountries({ quote: vi.fn((m, d) => Promise.resolve(d?.country === 'IN' && d.postal_code ? RATED : NO_RATES)), checkout });
    await screen.findByLabelText('Country / Region');
    await user.type(screen.getByLabelText('Address line 1'), '12 Kambam Main Road');
    await user.type(screen.getByLabelText('City / Town'), 'Cumbum');
    await user.selectOptions(screen.getByLabelText('State / union territory'), 'TN');
    await user.type(screen.getByLabelText('PIN code'), '625521');
    await user.type(screen.getByLabelText('Mobile number'), '98765 43210');
    expect(await screen.findByText('Standard (4–7 days) — ₹120.00')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Review order' }));
    expect(await screen.findByText('Prices in Indian rupees (₹).')).toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Place order · ₹2,119.00' }));
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/orders/SA-50077/pay'));
    expect(checkout.mock.calls[0][0]).toMatchObject({ expectedTotalCents: 211900, shipping: { country: 'IN', region: 'TN', postal_code: '625521',
      city: 'Cumbum', phone: '98765 43210', line2: null } });
    expect(api.quote).toHaveBeenCalled();
  });

  it('a returning US customer gets the US form by default and the US request is unchanged apart from country', async () => {
    const user = userEvent.setup();
    const checkout = vi.fn().mockResolvedValue({ order: { order_number: 'SA-50078' } });
    setupCountries({ defaultCountry: 'US', checkout });
    expect(await screen.findByLabelText('Country / Region')).toHaveValue('US');
    expect(await screen.findByText('Expedited (2-day) — $14.95')).toBeInTheDocument();
    await fillAddress(user);
    await user.click(screen.getByRole('button', { name: 'Review order' }));
    expect(await screen.findByText(/Boulder, Colorado 80302, United States/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Place order · $45.95' }));
    await waitFor(() => expect(checkout).toHaveBeenCalled());
    expect(checkout.mock.calls[0][0].shipping).toEqual({ full_name: 'Test Shopper Jr', line1: '1 Trail Way', line2: null, city: 'Boulder',
      region: 'CO', postal_code: '80302', country: 'US' });
  });

  it('India without approved INR prices: no amounts in any currency, a clear notice, ordering blocked', async () => {
    const user = userEvent.setup();
    setupCountries({ quote: vi.fn((m, d) => Promise.resolve(d?.country === 'IN' ? NO_PRICES : QUOTE)) });
    await screen.findByLabelText('Country / Region');
    await user.type(screen.getByLabelText('Address line 1'), '12 Kambam Main Road');
    await user.type(screen.getByLabelText('City / Town'), 'Cumbum');
    await user.type(screen.getByLabelText('Mobile number'), '98765 43210');
    await user.selectOptions(screen.getByLabelText('State / union territory'), 'TN');
    await user.type(screen.getByLabelText('PIN code'), '625521');
    expect(await screen.findByText(/Prices in Indian rupees \(₹\) haven’t been set by Summit Trail Co\. yet/)).toHaveTextContent('never converted from US dollars');
    expect(screen.getAllByText('Not set')).toHaveLength(2);                                  // subtotal and total
    expect(document.body.textContent).not.toMatch(/\$|₹\d/);
    await user.click(screen.getByRole('button', { name: 'Review order' }));
    expect(await screen.findByText('Price not set')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Place order' })).toBeDisabled();
  });

  it('an older server sending US-dollar amounts for India: none of them is shown', async () => {
    const usdForIndia = { ...QUOTE };                     // no currency information, USD figures
    delete usdForIndia.currency;
    delete usdForIndia.prices_available;
    setupCountries({ quote: vi.fn().mockResolvedValue(usdForIndia) });
    await screen.findByLabelText('Country / Region');
    expect(await screen.findByText(/haven’t been set/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('$');
  });

  it('if the delivery countries cannot be loaded it says so — never a silent US-only form', async () => {
    const user = userEvent.setup();
    const addressOptions = vi.fn().mockRejectedValueOnce(apiError('Not found.', 404, 'not_found'))
      .mockResolvedValueOnce({ countries: [INDIA, USA], default_country: 'IN' });
    setup({ api: { addressOptions, quote: vi.fn().mockResolvedValue(NO_RATES) } });
    expect(await screen.findByRole('alert')).toHaveTextContent('delivery countries couldn’t be loaded');
    expect(screen.queryByLabelText('ZIP code')).not.toBeInTheDocument();
    expect(screen.queryByText('United States addresses only.')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByLabelText('PIN code')).toBeInTheDocument();
  });

  it('India-only store (one country): no country choice, the Indian form, prices in rupees', async () => {
    const RATED = { ...NO_RATES, shipping_options: [{ method: 'standard', label: 'Standard delivery', cents: 14900, price: '₹149.00' }],
      shipping_cents: 14900, shipping: '₹149.00', total: '₹2,148.00', total_cents: 214800, shipping_available: true,
      total_excludes_shipping: false, can_checkout: true };
    setup({ api: { addressOptions: vi.fn().mockResolvedValue({ countries: [{ ...INDIA, shipping_configured: true, prices_configured: true }],
      default_country: 'IN' }), quote: vi.fn().mockResolvedValue(RATED) } });
    expect(await screen.findByTestId('ship-country')).toHaveTextContent('Delivering to India');
    expect(screen.queryByLabelText('Country / Region')).not.toBeInTheDocument();
    expect(screen.getByLabelText('PIN code')).toBeRequired();
    expect(screen.getByLabelText('Mobile number')).toBeRequired();
    expect(await screen.findByText('Standard delivery — ₹149.00')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\$|Expedited|United States/);
  });
});

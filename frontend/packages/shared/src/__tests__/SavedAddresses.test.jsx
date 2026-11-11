import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CheckoutPage from '../pages/CheckoutPage.jsx';
import AccountPage from '../pages/AccountPage.jsx';
import { createApi } from '../api.js';
import { makeApi, makeStore, renderAt } from './helpers.jsx';

const store = vi.hoisted(() => ({ value: null }));
vi.mock('../StoreApp.jsx', () => ({ useStore: () => store.value }));

const INDIA = {
  code: 'IN',
  name: 'India',
  currency: 'INR',
  line1_label: 'Address line 1',
  line2_label: 'Address line 2 / Landmark (optional)',
  city_label: 'City / Town',
  region_label: 'State / union territory',
  regions: [
    { code: 'TN', name: 'Tamil Nadu', kind: 'state' },
    { code: 'KA', name: 'Karnataka', kind: 'state' },
  ],
  postal_label: 'PIN code',
  postal_pattern: '^[1-9][0-9]{5}$',
  postal_example: '625521',
  phone: { required: true, pattern: '^(\\+?91)?[6-9]\\d{9}$', example: '98765 43210', dial_code: '+91' },
};

const QUOTE = {
  items: [{ slug: 'lumen-300-headlamp', name: 'Lumen 300 Headlamp', quantity: 1, line_total: '₹1,999.00', unit_price: '₹1,999.00' }],
  shipping_options: [{ method: 'standard', label: 'Standard delivery', cents: 12000, price: '₹120.00' }],
  shipping_method: 'standard',
  shipping_cents: 12000,
  shipping: '₹120.00',
  subtotal: '₹1,999.00',
  total: '₹2,119.00',
  total_cents: 211900,
  problems: [],
  can_checkout: true,
  currency: 'INR',
  prices_available: true,
  shipping_available: true,
};

const HOME_ADDRESS = {
  id: 101,
  label: 'Home',
  full_name: 'Priya Raman',
  line1: '12 Kambam Main Road',
  line2: 'Near Bus Stand',
  city: 'Cumbum',
  region: 'TN',
  postal_code: '625521',
  country: 'IN',
  phone: '+919876543210',
  is_default: true,
};

const WORK_ADDRESS = {
  id: 102,
  label: 'Work',
  full_name: 'Priya Raman',
  line1: '500 Anna Salai',
  line2: 'Tech Park Floor 4',
  city: 'Chennai',
  region: 'TN',
  postal_code: '600002',
  country: 'IN',
  phone: '+919876512345',
  is_default: false,
};

describe('Saved Address Management at Checkout', () => {
  it('automatically loads default address and pre-fills details without re-entry', async () => {
    const api = makeApi({
      quote: vi.fn().mockResolvedValue(QUOTE),
      addressOptions: vi.fn().mockResolvedValue({ countries: [INDIA], default_country: 'IN' }),
      addresses: vi.fn().mockResolvedValue({ addresses: [HOME_ADDRESS, WORK_ADDRESS] }),
    });
    store.value = makeStore({ storeId: 'store-a', api });
    renderAt(<CheckoutPage />, { path: '/checkout', route: '/checkout' });

    // Displays the saved address card with Default badge
    expect(await screen.findByTestId('checkout-saved-addresses')).toBeInTheDocument();
    expect(screen.getAllByText('Priya Raman').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('12 Kambam Main Road')).toBeInTheDocument();
    expect(screen.getByText('Cumbum, TN 625521')).toBeInTheDocument();
    expect(screen.getByText('Default')).toBeInTheDocument();
    expect(screen.getByText('Home')).toBeInTheDocument();
    expect(screen.getByText('Work')).toBeInTheDocument();

    // Clicking "Deliver to this address" advances straight to Review
    const user = userEvent.setup();
    const deliverBtns = screen.getAllByRole('button', { name: /Deliver to this address/i });
    await user.click(deliverBtns[0]);

    // Review step is now displayed
    expect(await screen.findByText('Review your order')).toBeInTheDocument();
    expect(screen.getByText(/12 Kambam Main Road/)).toBeInTheDocument();
    expect(screen.getByText(/Cumbum, Tamil Nadu 625521/)).toBeInTheDocument();
  });

  it('allows customer to switch to another saved address (e.g. Work)', async () => {
    const api = makeApi({
      quote: vi.fn().mockResolvedValue(QUOTE),
      addressOptions: vi.fn().mockResolvedValue({ countries: [INDIA], default_country: 'IN' }),
      addresses: vi.fn().mockResolvedValue({ addresses: [HOME_ADDRESS, WORK_ADDRESS] }),
    });
    store.value = makeStore({ storeId: 'store-a', api });
    renderAt(<CheckoutPage />, { path: '/checkout', route: '/checkout' });

    await screen.findByTestId('checkout-saved-addresses');

    // Deliver to Work address
    const user = userEvent.setup();
    const workCard = screen.getByTestId('address-card-102');
    const deliverWorkBtn = within(workCard).getByRole('button', { name: /Deliver to this address/i });
    await user.click(deliverWorkBtn);

    // Review displays Work address
    expect(await screen.findByText('Review your order')).toBeInTheDocument();
    expect(screen.getByText(/500 Anna Salai/)).toBeInTheDocument();
    expect(screen.getByText(/Chennai, Tamil Nadu 600002/)).toBeInTheDocument();
  });

  it('allows customer to switch to manual address entry form and back', async () => {
    const api = makeApi({
      quote: vi.fn().mockResolvedValue(QUOTE),
      addressOptions: vi.fn().mockResolvedValue({ countries: [INDIA], default_country: 'IN' }),
      addresses: vi.fn().mockResolvedValue({ addresses: [HOME_ADDRESS] }),
    });
    store.value = makeStore({ storeId: 'store-a', api });
    renderAt(<CheckoutPage />, { path: '/checkout', route: '/checkout' });

    await screen.findByTestId('checkout-saved-addresses');
    const user = userEvent.setup();

    // Click "+ Add a new address"
    const addBtn = screen.getAllByRole('button', { name: /\+ Add a new address/i })[0];
    await user.click(addBtn);

    // Form is now visible
    expect(screen.getByLabelText('Address line 1')).toBeInTheDocument();
    expect(screen.getByLabelText('Save this address to your account')).toBeInTheDocument();

    // Click "← Use a saved address"
    const backBtn = screen.getByRole('button', { name: /← Use a saved address/i });
    await user.click(backBtn);

    // Returned to saved addresses
    expect(await screen.findByTestId('checkout-saved-addresses')).toBeInTheDocument();
  });

  it('delivering to a saved address does not ask the server to save it again', async () => {
    const user = userEvent.setup();
    const checkoutMock = vi.fn().mockResolvedValue({ order: { order_number: 'SA-50010' } });
    const api = makeApi({
      quote: vi.fn().mockResolvedValue(QUOTE),
      addressOptions: vi.fn().mockResolvedValue({ countries: [INDIA], default_country: 'IN' }),
      addresses: vi.fn().mockResolvedValue({ addresses: [HOME_ADDRESS] }),
      checkout: checkoutMock,
    });
    store.value = makeStore({ storeId: 'store-a', api });
    renderAt(<CheckoutPage />, { path: '/checkout', route: '/checkout' });

    const deliverBtns = await screen.findAllByRole('button', { name: /Deliver to this address/i });
    await user.click(deliverBtns[0]);

    // Place order
    const placeBtn = await screen.findByRole('button', { name: /Place order/i });
    await user.click(placeBtn);

    await waitFor(() => {
      expect(checkoutMock).toHaveBeenCalledWith(
        expect.objectContaining({
          saveAddress: false,
          makeDefault: false,
          shipping: expect.objectContaining({
            line1: '12 Kambam Main Road',
            postal_code: '625521',
          }),
        })
      );
    });
  });
});

describe('Saving the checkout address is opt-in', () => {
  function setupForm(checkoutMock) {
    const api = makeApi({
      quote: vi.fn().mockResolvedValue(QUOTE),
      addressOptions: vi.fn().mockResolvedValue({ countries: [INDIA], default_country: 'IN' }),
      addresses: vi.fn().mockResolvedValue({ addresses: [] }),     // no saved addresses: the address form is shown
      checkout: checkoutMock,
    });
    store.value = makeStore({ storeId: 'store-a', api });
    renderAt(<CheckoutPage />, { path: '/checkout', route: '/checkout' });
  }

  async function fillAndReview(user) {
    await user.type(await screen.findByLabelText('Address line 1'), '12 Kambam Main Road');
    await user.type(screen.getByLabelText('City / Town'), 'Cumbum');
    await user.selectOptions(screen.getByLabelText(/State/), 'TN');
    await user.type(screen.getByLabelText('PIN code'), '625521');
    await user.type(screen.getByLabelText('Mobile number'), '9876543210');
  }

  async function placeOrder(user) {
    await user.click(screen.getByRole('button', { name: 'Review order' }));
    await user.click(await screen.findByRole('button', { name: /Place order/i }));
  }

  it('leaves "Save this address" unchecked and does not save unless the customer ticks it', async () => {
    const user = userEvent.setup();
    const checkoutMock = vi.fn().mockResolvedValue({ order: { order_number: 'SA-50011' } });
    setupForm(checkoutMock);
    await fillAndReview(user);
    expect(screen.getByLabelText('Save this address to your account')).not.toBeChecked();
    expect(screen.queryByLabelText('Make this my default address')).not.toBeInTheDocument();
    await placeOrder(user);
    await waitFor(() => expect(checkoutMock).toHaveBeenCalledTimes(1));
    expect(checkoutMock.mock.calls[0][0]).toMatchObject({ saveAddress: false, makeDefault: false });
  });

  it('sends saveAddress (and makeDefault) only when the customer ticks them', async () => {
    const user = userEvent.setup();
    const checkoutMock = vi.fn().mockResolvedValue({ order: { order_number: 'SA-50012' } });
    setupForm(checkoutMock);
    await fillAndReview(user);
    await user.click(screen.getByLabelText('Save this address to your account'));
    await user.click(screen.getByLabelText('Make this my default address'));
    await placeOrder(user);
    await waitFor(() => expect(checkoutMock).toHaveBeenCalledTimes(1));
    expect(checkoutMock.mock.calls[0][0]).toMatchObject({ saveAddress: true, makeDefault: true });
  });

  it('a ticked "make default" is not sent once "save" is unticked again', async () => {
    const user = userEvent.setup();
    const checkoutMock = vi.fn().mockResolvedValue({ order: { order_number: 'SA-50013' } });
    setupForm(checkoutMock);
    await fillAndReview(user);
    await user.click(screen.getByLabelText('Save this address to your account'));
    await user.click(screen.getByLabelText('Make this my default address'));
    await user.click(screen.getByLabelText('Save this address to your account'));
    await placeOrder(user);
    await waitFor(() => expect(checkoutMock).toHaveBeenCalledTimes(1));
    expect(checkoutMock.mock.calls[0][0]).toMatchObject({ saveAddress: false, makeDefault: false });
  });
});

describe('api.checkout request body', () => {
  async function sentBody(args) {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ order: { order_number: 'SA-1' } }) });
    vi.stubGlobal('fetch', fetchMock);
    try {
      await createApi('store-a').checkout({ shipping: { line1: 'x' }, shippingMethod: 'standard', expectedTotalCents: 100,
        idempotencyKey: 'k'.repeat(20), ...args });
    } finally {
      vi.unstubAllGlobals();
    }
    return JSON.parse(fetchMock.mock.calls[0][1].body);
  }

  it('omits save_address and its options unless saving was chosen', async () => {
    for (const args of [{}, { saveAddress: false }, { saveAddress: false, makeDefault: true, addressLabel: 'Work' }]) {
      const body = await sentBody(args);
      expect(body).not.toHaveProperty('save_address');
      expect(body).not.toHaveProperty('make_default');
      expect(body).not.toHaveProperty('address_label');
      expect(body).toMatchObject({ shipping_method: 'standard', expected_total_cents: 100 });
    }
  });

  it('sends save_address=true with its options when saving was chosen', async () => {
    expect(await sentBody({ saveAddress: true, makeDefault: true, addressLabel: 'Work' }))
      .toMatchObject({ save_address: true, make_default: true, address_label: 'Work' });
    expect(await sentBody({ saveAddress: true }))
      .toMatchObject({ save_address: true, make_default: false, address_label: 'Home' });
  });
});

describe('Account Address Book Management (AccountPage)', () => {
  it('renders address book and allows adding a new address', async () => {
    const user = userEvent.setup();
    const createMock = vi.fn().mockResolvedValue({ address: HOME_ADDRESS });
    const api = makeApi({
      myOrders: vi.fn().mockResolvedValue({ orders: [] }),
      addresses: vi.fn().mockResolvedValue({ addresses: [] }),
      addressOptions: vi.fn().mockResolvedValue({ countries: [INDIA], default_country: 'IN' }),
      createAddress: createMock,
    });
    store.value = makeStore({ storeId: 'store-a', api });
    renderAt(<AccountPage />, { path: '/account', route: '/account' });

    expect(await screen.findByText('Address Book')).toBeInTheDocument();
    expect(screen.getByText(/No saved addresses yet/i)).toBeInTheDocument();

    // Click "+ Add address"
    await user.click(screen.getByRole('button', { name: /\+ Add address/i }));

    // Address form appears
    expect(await screen.findByTestId('address-form')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Full name'), 'Jr');
    await user.type(screen.getByLabelText('Address line 1'), '12 Kambam Main Road');
    await user.type(screen.getByLabelText('City / Town'), 'Cumbum');
    await user.selectOptions(screen.getByLabelText(/State/), 'TN');
    await user.type(screen.getByLabelText('PIN code'), '625521');
    await user.type(screen.getByLabelText('Mobile number'), '9876543210');

    // Submit form
    await user.click(screen.getByRole('button', { name: 'Save address' }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          full_name: expect.stringContaining('Jr'),
          line1: '12 Kambam Main Road',
          city: 'Cumbum',
          region: 'TN',
          postal_code: '625521',
        })
      );
    });
  });

  it('allows setting default address and deleting an address', async () => {
    const user = userEvent.setup();
    const setDefaultMock = vi.fn().mockResolvedValue({ ok: true });
    const deleteMock = vi.fn().mockResolvedValue(null);
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    const api = makeApi({
      myOrders: vi.fn().mockResolvedValue({ orders: [] }),
      addresses: vi.fn().mockResolvedValue({ addresses: [HOME_ADDRESS, WORK_ADDRESS] }),
      setDefaultAddress: setDefaultMock,
      deleteAddress: deleteMock,
    });
    store.value = makeStore({ storeId: 'store-a', api });
    renderAt(<AccountPage />, { path: '/account', route: '/account' });

    expect(await screen.findByText('Address Book')).toBeInTheDocument();

    // Set Work as default
    const setDefBtn = screen.getByRole('button', { name: /Set as default address/i });
    await user.click(setDefBtn);
    expect(setDefaultMock).toHaveBeenCalledWith(102);

    // Delete Home address
    const homeCard = screen.getByTestId('address-card-101');
    const deleteBtn = within(homeCard).getByRole('button', { name: /Delete/i });
    await user.click(deleteBtn);
    expect(deleteMock).toHaveBeenCalledWith(101);
  });
});

import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StaffOrderPage, StaffOrdersPage } from '../pages/StaffPages.jsx';
import { apiError, makeApi, makeStore, renderAt } from './helpers.jsx';

const store = vi.hoisted(() => ({ value: null }));
vi.mock('../StoreApp.jsx', () => ({ useStore: () => store.value }));

const AGENT = { token: 't', customer: { name: 'Summit Support Agent', role: 'agent', email: 'agent@summittrail.example.com' } };
const ROW = { order_number: 'SA-50020', customer_name: 'Pat Shopper', placed_at: '2026-11-09T10:00:00+00:00', item_count: 2,
  total: '$45.95', status: 'processing', status_label: 'being prepared', actions: ['ship'] };
const ORDER = { ...ROW, items: [{ name: 'Lumen 300 Headlamp', slug: 'lumen-300-headlamp', quantity: 1, line_total: '$39.00' }],
  shipping_method: 'standard', shipping_address: { name: 'Pat Shopper', line1: '1 Trail Way', city: 'Boulder', region: 'CO', postal_code: '80302' },
  carrier: null, tracking_number: null, tracking_url: null,
  history: [{ from_status: null, status: 'pending_payment', status_label: 'awaiting payment', at: '2026-11-09T10:00:00+00:00', actor_role: 'customer', actor_name: 'Pat Shopper', note: 'order placed' },
    { from_status: 'pending_payment', status: 'processing', status_label: 'being prepared', at: '2026-11-09T10:01:00+00:00', actor_role: 'system', actor_name: 'System', note: 'payment confirmed' }] };

function setupList({ session = AGENT, api = {}, path = '/staff/orders' } = {}) {
  const a = makeApi({ staffOrders: vi.fn().mockResolvedValue({ orders: [ROW], total: 1 }), ...api });
  store.value = makeStore({ api: a, session });
  renderAt(<StaffOrdersPage />, { path, route: '/staff/orders' });
  return a;
}

function setupOrder({ order = ORDER, api = {} } = {}) {
  const a = makeApi({ staffOrder: vi.fn().mockResolvedValue({ order }), staffAction: vi.fn(), ...api });
  store.value = makeStore({ api: a, session: AGENT });
  renderAt(<StaffOrderPage />, { path: `/staff/orders/${order.order_number}`, route: '/staff/orders/:number' });
  return a;
}

describe('staff pages: access', () => {
  it('refuses customer accounts without calling the API', () => {
    const api = setupList({ session: { token: 't', customer: { name: 'Pat', role: 'customer' } } });
    expect(screen.getByRole('heading', { name: 'Staff only' })).toBeInTheDocument();
    expect(api.staffOrders).not.toHaveBeenCalled();
  });

  it('asks a signed-out visitor to sign in', () => {
    setupList({ session: null });
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/account?next=/staff/orders');
  });
});

describe('staff order list', () => {
  it('defaults to orders to ship and filters by status and search', async () => {
    const user = userEvent.setup();
    const api = setupList();
    const table = await screen.findByRole('table');
    expect(within(table).getByRole('link', { name: 'SA-50020' })).toHaveAttribute('href', '/staff/orders/SA-50020');
    expect(api.staffOrders).toHaveBeenLastCalledWith({ status: ['processing'], q: '', limit: 25, offset: 0 });
    await user.click(screen.getByRole('button', { name: 'In transit' }));
    await waitFor(() => expect(api.staffOrders).toHaveBeenLastCalledWith({ status: ['shipped', 'out_for_delivery'], q: '', limit: 25, offset: 0 }));
    await user.type(screen.getByLabelText('Search by order number or customer name'), 'Pat{Enter}');
    await waitFor(() => expect(api.staffOrders).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'Pat' })));
  });

  it('shows the server error', async () => {
    setupList({ api: { staffOrders: vi.fn().mockRejectedValue(apiError('Staff access required.', 403)) } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Staff access required.');
  });
});

describe('staff order page', () => {
  it('ships with carrier, tracking and the status the screen showed', async () => {
    const user = userEvent.setup();
    const shipped = { ...ORDER, status: 'shipped', status_label: 'shipped', actions: ['out_for_delivery', 'deliver', 'return'], carrier: 'Blue Dart', tracking_number: 'BD1234' };
    const api = setupOrder({ api: { staffAction: vi.fn().mockResolvedValue({ order: shipped }) } });
    await screen.findByRole('heading', { level: 1, name: 'Order SA-50020' });
    expect(screen.getByText(/order placed/)).toBeInTheDocument();
    await user.type(screen.getByLabelText('Carrier'), 'Blue Dart');
    await user.type(screen.getByLabelText('Tracking number'), 'BD1234');
    await user.type(screen.getByLabelText(/Tracking link/), 'https://track.example.org/BD1234');
    await user.click(screen.getByRole('button', { name: 'Mark as shipped' }));
    expect(api.staffAction).toHaveBeenCalledWith('SA-50020', 'ship', expect.objectContaining({
      expected_status: 'processing', carrier: 'Blue Dart', tracking_number: 'BD1234', tracking_url: 'https://track.example.org/BD1234' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Order SA-50020 is now shipped.');
    expect(screen.getByRole('button', { name: 'Mark as delivered' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Order SA-50020' })).toHaveFocus();
  });

  it('a return needs a reason', async () => {
    setupOrder({ order: { ...ORDER, status: 'delivered', status_label: 'delivered', actions: ['return'] } });
    const note = await screen.findByLabelText('Return reason (required)');
    expect(note).toBeRequired();
    expect(screen.queryByRole('button', { name: 'Mark as shipped' })).not.toBeInTheDocument();
  });

  it('explains a stale screen and offers a reload', async () => {
    const user = userEvent.setup();
    const staffOrder = vi.fn().mockResolvedValue({ order: { ...ORDER, status: 'shipped', status_label: 'shipped', actions: ['out_for_delivery', 'deliver', 'return'] } });
    const api = setupOrder({ api: { staffOrder, staffAction: vi.fn().mockRejectedValue(apiError('This order is now “delivered”. Reload it before changing it.', 409, 'stale_status')) } });
    await user.click(await screen.findByRole('button', { name: 'Mark as delivered' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Reload it before changing it.');
    await user.click(screen.getByRole('button', { name: 'Reload order' }));
    await waitFor(() => expect(api.staffOrder).toHaveBeenCalledTimes(2));
  });

  it('closed orders offer no action', async () => {
    setupOrder({ order: { ...ORDER, status: 'cancelled', status_label: 'cancelled', actions: [] } });
    expect(await screen.findByText('No fulfilment step is available for an order that is cancelled.')).toBeInTheDocument();
  });

  it('an order from another store or a missing one is not found', async () => {
    setupOrder({ api: { staffOrder: vi.fn().mockRejectedValue(apiError('Order not found.', 404)) } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Order not found in this store.');
  });
});

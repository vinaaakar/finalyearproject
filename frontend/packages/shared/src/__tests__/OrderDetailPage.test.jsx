import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OrderDetailPage from '../pages/OrderDetailPage.jsx';
import { apiError, makeApi, makeStore, renderAt } from './helpers.jsx';

const store = vi.hoisted(() => ({ value: null }));
vi.mock('../StoreApp.jsx', () => ({ useStore: () => store.value }));

const ORDER = {
  order_number: 'SA-50010', status: 'shipped', status_label: 'shipped', carrier: 'UPS', tracking_number: '1ZTEST', tracking_url: null,
  estimated_delivery: '2026-11-12', total: '$85.95', subtotal: '$79.00', shipping: '$6.95', shipping_method: 'standard',
  placed_at: '2026-11-09T10:00:00+00:00', updated_at: '2026-11-09T12:00:00+00:00', awaiting_payment: false,
  items: [{ name: 'Daytrip 22L Daypack', slug: 'daytrip-22l-daypack', quantity: 1, unit_price: '$79.00', line_total: '$79.00' }],
  shipping_address: { name: 'Test Shopper', line1: '1 Trail Way', line2: null, city: 'Boulder', region: 'CO', postal_code: '80302', country: 'US' },
};

function setup({ order = ORDER, api = {}, session, storeId = 'store-a' } = {}) {
  const a = makeApi({ order: vi.fn().mockResolvedValue({ order }), ...api });
  store.value = makeStore({ storeId, api: a, ...(session !== undefined ? { session } : {}) });
  renderAt(<OrderDetailPage />, { path: `/orders/${order.order_number}`, route: '/orders/:number' });
  return a;
}

describe('OrderDetailPage', () => {
  it('asks a signed-out visitor to sign in and does not request the order', () => {
    const api = setup({ session: null });
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/account?next=/orders/SA-50010');
    expect(api.order).not.toHaveBeenCalled();
  });

  it('shows items, totals, address, tracking and progress', async () => {
    const api = setup();
    expect(await screen.findByRole('heading', { level: 1, name: 'Order SA-50010' })).toBeInTheDocument();
    expect(api.order).toHaveBeenCalledWith('SA-50010');
    const items = screen.getByRole('region', { name: 'Items' });
    expect(within(items).getByRole('link', { name: 'Daytrip 22L Daypack' })).toHaveAttribute('href', '/products/daytrip-22l-daypack');
    expect(within(items).getByText('$85.95')).toBeInTheDocument();
    const delivery = screen.getByRole('region', { name: 'Delivery' });
    expect(within(delivery).getByText(/1 Trail Way/)).toBeInTheDocument();
    expect(within(delivery).getByText(/UPS · 1ZTEST/)).toBeInTheDocument();
    const progress = screen.getByRole('list', { name: 'Order progress' });
    expect(within(progress).getByText('Shipped').closest('li')).toHaveAttribute('aria-current', 'step');
    expect(within(progress).getAllByText('(completed)')).toHaveLength(2);
  });

  it('links the tracking number when the carrier gives a tracking URL', async () => {
    setup({ order: { ...ORDER, tracking_url: 'https://carrier.example/track?n=1ZTEST' } });
    const link = await screen.findByRole('link', { name: /Track 1ZTEST/ });
    expect(link).toHaveAttribute('href', 'https://carrier.example/track?n=1ZTEST');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('offers payment for an unpaid order', async () => {
    setup({ order: { ...ORDER, status: 'pending_payment', status_label: 'awaiting payment', awaiting_payment: true, carrier: null, tracking_number: null } });
    expect(await screen.findByRole('link', { name: 'Pay now' })).toHaveAttribute('href', '/orders/SA-50010/pay');
    expect(screen.getByText('Tracking details appear here once the order ships.')).toBeInTheDocument();
  });

  it('explains a returned order without claiming a refund', async () => {
    setup({ order: { ...ORDER, status: 'returned', status_label: 'returned' } });
    const note = await screen.findByText(/marked as returned/);
    expect(note).toHaveTextContent("can’t show refund status");
    expect(screen.queryByRole('list', { name: 'Order progress' })).not.toBeInTheDocument();
  });

  it('shows status history when the server provides it', async () => {
    setup({ order: { ...ORDER, history: [{ status: 'processing', status_label: 'being prepared', at: '2026-11-09T10:05:00+00:00', note: null },
      { status: 'shipped', status_label: 'shipped', at: '2026-11-09T12:00:00+00:00', note: 'UPS 1ZTEST' }] } });
    const history = await screen.findByRole('region', { name: 'Status updates' });
    expect(within(history).getAllByRole('listitem')).toHaveLength(2);
    expect(within(history).getByText(/UPS 1ZTEST/)).toBeInTheDocument();
  });

  it('treats a missing or foreign order as not found', async () => {
    setup({ api: { order: vi.fn().mockRejectedValue(apiError('Order not found.', 404)) } });
    expect(await screen.findByRole('heading', { name: 'Order not found' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Your orders' })).toHaveAttribute('href', '/account');
  });

  it('shows a network error with a retry that reloads', async () => {
    const order = vi.fn().mockRejectedValueOnce(apiError('Cannot reach the server.', 0, 'network')).mockResolvedValueOnce({ order: ORDER });
    setup({ api: { order } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the server.');
    await userEvent.setup().click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Order SA-50010' })).toBeInTheDocument();
    expect(order).toHaveBeenCalledTimes(2);
  });
});

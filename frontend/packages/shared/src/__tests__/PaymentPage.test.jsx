import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PaymentPage from '../pages/PaymentPage.jsx';
import { apiError, deferred, makeApi, makeStore, renderAt } from './helpers.jsx';

const store = vi.hoisted(() => ({ value: null }));
vi.mock('../StoreApp.jsx', () => ({ useStore: () => store.value }));

const NUMBER = 'SA-50001';
const pendingOrder = (extra = {}) => ({ order_number: NUMBER, status: 'pending_payment', status_label: 'awaiting payment', total: '$45.95', items: [], ...extra });

function setup({ order = pendingOrder(), payment = null, session, storeId = 'store-a', api = {} } = {}) {
  const a = makeApi({
    order: vi.fn().mockResolvedValue({ order }),
    paymentStatus: vi.fn().mockResolvedValue({ payment }),
    ...api,
  });
  store.value = makeStore({ storeId, api: a, ...(session !== undefined ? { session } : {}) });
  renderAt(<PaymentPage />, { path: `/orders/${NUMBER}/pay`, route: '/orders/:number/pay' });
  return a;
}

describe.each(['store-a', 'store-b'])('PaymentPage (%s)', (storeId) => {
  it('asks a signed-out visitor to sign in and loads nothing', () => {
    const api = setup({ session: null, storeId });
    expect(screen.getByText(/to see this order/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'sign in' })).toHaveAttribute('href', '/account');
    expect(api.order).not.toHaveBeenCalled();
  });

  it('shows a loading state until the order arrives', async () => {
    const pending = deferred();
    setup({ storeId, api: { order: vi.fn(() => pending.promise) } });
    expect(screen.getByText('Loading…')).toBeInTheDocument();
    pending.resolve({ order: pendingOrder() });
    expect(await screen.findByRole('heading', { name: 'Payment' })).toBeInTheDocument();
  });

  it('shows the server error when the order cannot be loaded', async () => {
    setup({ storeId, api: { order: vi.fn().mockRejectedValue(apiError('Order not found.', 404, 'not_found')) } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Order not found.');
  });
});

describe('PaymentPage payment states', () => {
  it('offers a test payment and labels sandbox mode', async () => {
    setup();
    expect(await screen.findByRole('button', { name: 'Pay $45.95 (test)' })).toBeEnabled();
    expect(screen.getByRole('note')).toHaveTextContent(/TEST MODE/);
  });

  it('confirms only after the server verifies an approved payment', async () => {
    const user = userEvent.setup();
    const payment = { status: 'pending', reference: 'sbx_abcdefghijklmnop', amount: '$45.95' };
    const api = setup({
      api: {
        startPayment: vi.fn().mockResolvedValue({ payment }),
        completeSandboxPayment: vi.fn().mockResolvedValue({}),
        verifyPayment: vi.fn().mockResolvedValue({ order: pendingOrder({ status: 'processing', status_label: 'being prepared' }),
                                                   payment: { ...payment, status: 'succeeded' } }),
      },
    });
    await user.click(await screen.findByRole('button', { name: 'Pay $45.95 (test)' }));
    await user.click(await screen.findByRole('button', { name: 'Simulate approved payment' }));
    expect(await screen.findByRole('heading', { name: 'Thank you!' })).toBeInTheDocument();
    expect(screen.getByText(/Payment confirmed by the \(sandbox\) payment provider/)).toBeInTheDocument();
    expect(api.completeSandboxPayment).toHaveBeenCalledWith(payment.reference, 'success');
    expect(api.verifyPayment).toHaveBeenCalledWith(NUMBER);
  });

  it('reports a declined payment and lets the customer try again', async () => {
    const user = userEvent.setup();
    const payment = { status: 'pending', reference: 'sbx_abcdefghijklmnop', amount: '$45.95' };
    setup({
      api: {
        startPayment: vi.fn().mockResolvedValue({ payment }),
        completeSandboxPayment: vi.fn().mockResolvedValue({}),
        verifyPayment: vi.fn().mockResolvedValue({ order: pendingOrder(), payment: { ...payment, status: 'failed' } }),
      },
    });
    await user.click(await screen.findByRole('button', { name: 'Pay $45.95 (test)' }));
    await user.click(await screen.findByRole('button', { name: 'Simulate declined payment' }));
    expect(await screen.findByText('The test payment was declined. You can try again.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Pay $45.95 (test)' })).toBeEnabled();
    expect(screen.queryByText(/Payment confirmed/)).not.toBeInTheDocument();
  });

  it('shows a payment start failure without changing the order', async () => {
    const user = userEvent.setup();
    setup({ api: { startPayment: vi.fn().mockRejectedValue(apiError('This order is not awaiting payment.', 409)) } });
    await user.click(await screen.findByRole('button', { name: 'Pay $45.95 (test)' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('This order is not awaiting payment.');
    expect(screen.getByRole('heading', { name: 'Payment' })).toBeInTheDocument();
  });
});

describe('PaymentPage cancellation', () => {
  it('explains what will happen and cancels only after explicit confirmation', async () => {
    const user = userEvent.setup();
    const api = setup({ api: { cancelOrder: vi.fn().mockResolvedValue({ order: pendingOrder({ status: 'cancelled', status_label: 'cancelled' }) }) } });
    await user.click(await screen.findByRole('button', { name: 'Cancel this order' }));
    const confirm = screen.getByRole('group', { name: `Confirm cancelling order ${NUMBER}` });
    expect(confirm).toHaveTextContent(`Cancel order ${NUMBER}?`);
    expect(confirm).toHaveTextContent('No payment has been taken for it');
    expect(confirm).toHaveTextContent('This can’t be undone.');
    expect(api.cancelOrder).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: `Yes, cancel order ${NUMBER}` }));
    expect(await screen.findByText(`Order ${NUMBER} has been cancelled. No payment was taken.`)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Order cancelled' })).toBeInTheDocument();
    expect(api.cancelOrder).toHaveBeenCalledTimes(1);
  });

  it('"Keep my order" closes the confirmation without calling the server', async () => {
    const user = userEvent.setup();
    const api = setup();
    await user.click(await screen.findByRole('button', { name: 'Cancel this order' }));
    await user.click(screen.getByRole('button', { name: 'Keep my order' }));
    expect(screen.queryByRole('group', { name: /Confirm cancelling/ })).not.toBeInTheDocument();
    expect(api.cancelOrder).not.toHaveBeenCalled();
  });

  it('moves focus into the confirmation and back to "Cancel this order" after "Keep my order"', async () => {
    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole('button', { name: 'Cancel this order' }));
    expect(screen.getByRole('group', { name: `Confirm cancelling order ${NUMBER}` })).toHaveFocus();
    await user.click(screen.getByRole('button', { name: 'Keep my order' }));
    expect(screen.getByRole('button', { name: 'Cancel this order' })).toHaveFocus();
  });

  it('mentions the in-flight test payment in the confirmation', async () => {
    const user = userEvent.setup();
    setup({ payment: { status: 'pending', reference: 'sbx_abcdefghijklmnop', amount: '$45.95' } });
    await user.click(await screen.findByRole('button', { name: 'Cancel this order' }));
    expect(screen.getByRole('group', { name: /Confirm cancelling/ })).toHaveTextContent('the test payment in progress will be cancelled too');
  });

  it('sends one cancellation even when the confirm button is double-clicked', async () => {
    const user = userEvent.setup();
    const pending = deferred();
    const api = setup({ api: { cancelOrder: vi.fn(() => pending.promise) } });
    await user.click(await screen.findByRole('button', { name: 'Cancel this order' }));
    const yes = screen.getByRole('button', { name: `Yes, cancel order ${NUMBER}` });
    await user.dblClick(yes);
    expect(await screen.findByRole('button', { name: 'Cancelling…' })).toBeDisabled();
    pending.resolve({ order: pendingOrder({ status: 'cancelled', status_label: 'cancelled' }) });
    expect(await screen.findByText(/has been cancelled/)).toBeInTheDocument();
    expect(api.cancelOrder).toHaveBeenCalledTimes(1);
  });

  it('does not claim success when the server does not report the order as cancelled', async () => {
    const user = userEvent.setup();
    setup({ api: { cancelOrder: vi.fn().mockResolvedValue({ order: pendingOrder() }) } });
    await user.click(await screen.findByRole('button', { name: 'Cancel this order' }));
    await user.click(screen.getByRole('button', { name: `Yes, cancel order ${NUMBER}` }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The order could not be cancelled');
    expect(screen.queryByText(/has been cancelled/)).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Payment' })).toBeInTheDocument();
  });

  it('shows the server refusal (e.g. already cancelled) and keeps the order unchanged', async () => {
    const user = userEvent.setup();
    setup({ api: { cancelOrder: vi.fn().mockRejectedValue(apiError('This order is already cancelled.', 409, 'already_cancelled')) } });
    await user.click(await screen.findByRole('button', { name: 'Cancel this order' }));
    await user.click(screen.getByRole('button', { name: `Yes, cancel order ${NUMBER}` }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('This order is already cancelled.'));
    expect(screen.queryByText(/No payment was taken\./)).not.toBeInTheDocument();
  });
});

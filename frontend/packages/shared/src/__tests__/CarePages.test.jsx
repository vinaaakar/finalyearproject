import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CareNewPage, CareRequestPage, CareRequestsPage } from '../pages/CarePages.jsx';
import { StaffCarePage, StaffCareRequestPage } from '../pages/StaffCarePages.jsx';
import ChatWidget from '../ChatWidget.jsx';
import { apiError, deferred, makeApi, makeStore, renderAt } from './helpers.jsx';

const store = vi.hoisted(() => ({ value: null }));
vi.mock('../StoreApp.jsx', () => ({ useStore: () => store.value }));

const AGENT = { customer: { name: 'Summit Support Agent', role: 'agent' } };
const ORDERS = { kind: 'return', categories: ['damaged', 'wrong_item', 'not_as_described', 'no_longer_needed', 'other'], simulated: false,
  orders: [{ order_number: 'SA-50001', status: 'delivered', eligible: true, reason: null, until: '2026-12-30', days: 60 },
    { order_number: 'SA-50002', status: 'processing', eligible: false, reason: 'not_delivered' }] };
const DETAIL = { ...ORDERS, order: { order_number: 'SA-50001', status: 'delivered', eligible: true, until: '2026-12-30', days: 60 },
  items: [{ id: 11, name: 'Lumen 300 Headlamp', quantity: 1, open_request: null }, { id: 12, name: 'PocketFlame Stove', quantity: 1, open_request: 'SA-RET-00004' }],
  open_for_order: null };
const REQUEST = { reference: 'SA-RET-00009', kind: 'return', category: 'damaged', description: 'Cracked lens', status: 'requested',
  status_label: 'Requested', order_number: 'SA-50001', item: { id: 11, name: 'Lumen 300 Headlamp', quantity: 1 }, created_at: '2026-11-11T05:00:00Z',
  open: true, simulated: false, simulated_notice: null, assigned: false, can_withdraw: true, can_reply: true,
  updates: [{ event: 'created', status: 'requested', status_label: 'Requested', message: null, by: 'you', at: '2026-11-11T05:00:00Z' }] };

function setup(element, { path, route, api = {}, session } = {}) {
  const a = makeApi(api);
  store.value = makeStore({ api: a, ...(session ? { session } : {}) });
  renderAt(element, { path, route });
  return a;
}

describe('Customer: new request', () => {
  it('shows eligibility, needs an item for a multi-item return, reviews, then sends once with one idempotency key', async () => {
    const user = userEvent.setup();
    const sent = deferred();
    const api = setup(<CareNewPage />, { path: '/support/new?kind=return', route: '/support/new', api: {
      careOptions: vi.fn((kind, order) => Promise.resolve(order ? DETAIL : ORDERS)), careCreate: vi.fn(() => sent.promise) } });
    const orderSelect = await screen.findByLabelText('Order');
    expect(within(orderSelect).getByRole('option', { name: 'SA-50002 — not delivered yet' })).toBeDisabled();
    await user.selectOptions(orderSelect, 'SA-50001');
    expect(await screen.findByText(/60-day returns policy, a return can be requested until 2026-12-30/)).toBeInTheDocument();
    expect(within(screen.getByLabelText('Item')).getByRole('option', { name: /already open: SA-RET-00004/ })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText('Reason'), 'damaged');
    await user.type(screen.getByLabelText('Describe it in your own words'), 'Cracked lens');
    expect(screen.getByRole('button', { name: 'Review' })).toBeDisabled();                   // item still missing
    await user.selectOptions(screen.getByLabelText('Item'), '11');
    await user.click(screen.getByRole('button', { name: 'Review' }));
    expect(screen.getByRole('heading', { name: 'Check before sending' })).toBeInTheDocument();
    expect(api.careCreate).not.toHaveBeenCalled();                                            // nothing sent before confirming
    await user.dblClick(screen.getByRole('button', { name: 'Confirm and send' }));
    expect(screen.getByRole('button', { name: 'Sending…' })).toBeDisabled();
    sent.resolve({ request: REQUEST, created: true });
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/support/requests/SA-RET-00009'));
    expect(api.careCreate).toHaveBeenCalledTimes(1);
    const [body, key] = api.careCreate.mock.calls[0];
    expect(body).toEqual({ kind: 'return', category: 'damaged', description: 'Cracked lens', order_number: 'SA-50001', item_id: 11 });
    expect(key.length).toBeGreaterThan(10);
  });

  it('refund requests say clearly that refunds are simulated; server refusals are shown and nothing is claimed', async () => {
    const user = userEvent.setup();
    setup(<CareNewPage />, { path: '/support/new?kind=refund', route: '/support/new', api: {
      careOptions: vi.fn((k, order) => Promise.resolve(order ? { ...DETAIL, kind: 'refund', categories: ['damaged', 'other'] }
        : { ...ORDERS, kind: 'refund', categories: ['damaged', 'other'] })),
      careCreate: vi.fn().mockRejectedValue(apiError('You already have an open request for this: SA-RFD-00002.', 409, 'duplicate_request')) } });
    expect(await screen.findByRole('note')).toHaveTextContent('no real money is transferred');
    await user.selectOptions(screen.getByLabelText('Order'), 'SA-50001');
    await user.selectOptions(await screen.findByLabelText('Reason'), 'damaged');
    await user.type(screen.getByLabelText('Describe it in your own words'), 'Broken');
    await user.click(screen.getByRole('button', { name: 'Review' }));
    await user.click(screen.getByRole('button', { name: 'Confirm and send' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('already have an open request');
    expect(screen.getByRole('button', { name: 'Review' })).toBeInTheDocument();             // back to the form
  });

  it('human help says no one is live and needs a signed-in customer', async () => {
    setup(<CareNewPage />, { path: '/support/new?kind=escalation', route: '/support/new', api: {
      careOptions: vi.fn().mockResolvedValue({ ...ORDERS, kind: 'escalation', categories: ['order_problem', 'other'] }) } });
    expect(await screen.findByRole('note')).toHaveTextContent('Nobody is available live');
    expect(screen.getByLabelText('Order (optional)')).not.toBeRequired();
  });
});

describe('Customer: requests', () => {
  it('lists the customer’s requests with their status', async () => {
    setup(<CareRequestsPage />, { api: { careRequests: vi.fn().mockResolvedValue({ requests: [REQUEST] }) } });
    expect(await screen.findByRole('link', { name: 'SA-RET-00009' })).toHaveAttribute('href', '/support/requests/SA-RET-00009');
    expect(screen.getByText('Requested')).toBeInTheDocument();
  });

  it('shows staff updates, sends a reply, and withdraws only after confirming', async () => {
    const user = userEvent.setup();
    const withStaff = { ...REQUEST, updates: [...REQUEST.updates, { event: 'message', status: null, status_label: null, message: 'Please send a photo.', by: 'staff', at: '2026-11-11T06:00:00Z' }] };
    const api = setup(<CareRequestPage />, { path: '/support/requests/SA-RET-00009', route: '/support/requests/:ref', api: {
      careRequest: vi.fn().mockResolvedValue({ request: withStaff }),
      careReply: vi.fn().mockResolvedValue({ request: withStaff }),
      careWithdraw: vi.fn().mockResolvedValue({ request: { ...withStaff, status: 'withdrawn', status_label: 'Withdrawn', can_withdraw: false, can_reply: false, open: false } }) } });
    expect(await screen.findByText('Please send a photo.')).toBeInTheDocument();
    expect(screen.getByText('Store team')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Send a message to the store team'), 'Photo attached by email');
    await user.click(screen.getByRole('button', { name: 'Send message' }));
    expect(api.careReply).toHaveBeenCalledWith('SA-RET-00009', 'Photo attached by email');
    await user.click(screen.getByRole('button', { name: 'Withdraw this request' }));
    expect(api.careWithdraw).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Yes, withdraw' }));
    expect(await screen.findByText('Request withdrawn.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Withdraw this request' })).not.toBeInTheDocument();
  });
});

describe('Staff: customer care', () => {
  it('queues: type tabs, status groups and search go to the server', async () => {
    const user = userEvent.setup();
    const api = setup(<StaffCarePage />, { path: '/staff/care', route: '/staff/care', session: AGENT, api: {
      staffCare: vi.fn().mockResolvedValue({ requests: [{ ...REQUEST, customer_name: 'Test Shopper', assigned_to: null }], total: 1 }) } });
    expect(await screen.findByRole('link', { name: 'SA-RET-00009' })).toBeInTheDocument();
    expect(api.staffCare.mock.calls[0][0]).toMatchObject({ kind: ['complaint'], status: expect.arrayContaining(['open', 'requested']) });
    await user.click(screen.getByRole('button', { name: 'Refunds (simulated)' }));
    await waitFor(() => expect(api.staffCare.mock.calls.at(-1)[0].kind).toEqual(['refund']));
    expect(screen.getByRole('note')).toHaveTextContent('no real money');
    await user.type(screen.getByLabelText('Search by request or order reference'), 'SA-50001');
    await user.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(api.staffCare.mock.calls.at(-1)[0].q).toBe('SA-50001'));
  });

  it('customers can’t see the staff screens', () => {
    setup(<StaffCarePage />, { path: '/staff/care', route: '/staff/care' });
    expect(screen.getByRole('heading', { name: 'Staff only' })).toBeInTheDocument();
  });

  it('a rejection needs a reason for the customer; the status call carries the status the screen showed', async () => {
    const user = userEvent.setup();
    const staffView = { ...REQUEST, customer: { name: 'Test Shopper', email: 't@example.com' }, assigned_to: null,
      order: { order_number: 'SA-50001', status: 'delivered', total: '₹1,048.00', payment: { status: 'succeeded', amount: '₹1,048.00' },
        delivered_at: '2026-11-10T05:00:00Z', items: [], return_eligibility: { eligible: true, until: '2026-12-30' } },
      actions: ['rejected', 'under_review'], reason_required_for: ['closed', 'rejected'],
      history: [{ event: 'note', visibility: 'internal', body: 'Check the seal', by: 'Summit Support Agent', role: 'agent', at: '2026-11-11T05:10:00Z' }] };
    const api = setup(<StaffCareRequestPage />, { path: '/staff/care/SA-RET-00009', route: '/staff/care/:ref', session: AGENT, api: {
      staffCareRequest: vi.fn().mockResolvedValue({ request: staffView }), staffCareAgents: vi.fn().mockResolvedValue({ agents: [{ id: 4, name: 'Summit Support Agent' }] }),
      staffCareStatus: vi.fn().mockResolvedValue({ request: { ...staffView, status: 'rejected', status_label: 'Rejected', actions: [] } }) } });
    expect(await screen.findByText('Check the seal')).toBeInTheDocument();
    expect(screen.getAllByText(/₹1,048\.00/).length).toBeGreaterThan(0);
    await user.click(screen.getByRole('radio', { name: 'Reject' }));
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    await user.type(screen.getByLabelText(/Message to the customer \(required/), 'The seal was opened.');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(api.staffCareStatus).toHaveBeenCalledWith('SA-RET-00009', { status: 'rejected', expected_status: 'requested', message: 'The seal was opened.' });
    expect(await screen.findByText('Status updated.')).toBeInTheDocument();
  });
});

describe('Chat: customer-care conversation', () => {
  const base = { products: [], orders: [], requires_login: false, source: 'rules', cart: null, language: 'en', language_status: 'detected', clarification: false };
  it('sends the server’s draft back, and the Confirm button sends “yes” — the reference shown comes from the server', async () => {
    const user = userEvent.setup();
    const draft = { kind: 'complaint', step: 'confirm', order: 'SA-50001', category: 'damaged', description: 'Broken', key: 'chat_abcdefghijklmnopqrst' };
    const chat = vi.fn()
      .mockResolvedValueOnce({ ...base, reply: 'Please check before I submit: Complaint — order SA-50001…', care_draft: draft,
        actions: [{ type: 'reply', label: 'Confirm and submit', text: 'yes' }, { type: 'reply', label: 'Cancel', text: 'cancel' }] })
      .mockResolvedValueOnce({ ...base, reply: 'Submitted. Your complaint reference is SA-CMP-00012. Status: Open.', care_draft: null,
        care_reference: 'SA-CMP-00012', actions: [{ type: 'link', to: '/support/requests/SA-CMP-00012', label: 'View SA-CMP-00012' }] });
    store.value = makeStore({ api: makeApi({ chat }) });
    renderAt(<ChatWidget open prefill="" onOpen={vi.fn()} onClose={vi.fn()} />);
    await user.type(screen.getByRole('textbox'), 'My headlamp arrived broken');
    await user.click(screen.getByRole('button', { name: 'அனுப்பு' }));
    await user.click(await screen.findByRole('button', { name: 'Confirm and submit' }));
    expect(await screen.findByText('Submitted. Your complaint reference is SA-CMP-00012. Status: Open.')).toBeInTheDocument();
    expect(chat.mock.calls[1][0]).toBe('yes');
    expect(chat.mock.calls[1][3].careDraft).toEqual(draft);                       // the draft went back to the server
    expect(chat.mock.calls[0][3].careDraft).toBeUndefined();
    expect(screen.getByRole('button', { name: 'View SA-CMP-00012' })).toBeInTheDocument();
  });
});

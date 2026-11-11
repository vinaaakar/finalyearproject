// Customer care for customers: complaints, return requests, SIMULATED refund requests and human help. The server checks
// every rule (ownership, eligibility from the store's own policy, duplicates, allowed status changes); these screens
// only collect the request, show a review before submitting, and show what the server recorded.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { newIdempotencyKey } from '../api.js';
import { useStore } from '../StoreApp.jsx';

export const KIND_LABELS = { complaint: 'Report a problem', return: 'Return an item', refund: 'Request a refund', escalation: 'Get human help' };
export const KIND_NAMES = { complaint: 'Complaint', return: 'Return request', refund: 'Refund request (simulated)', escalation: 'Human help request' };
export const CATEGORY_LABELS = {
  damaged: 'Damaged product', wrong_item: 'Wrong product received', missing_item: 'Missing item', quality: 'Product quality issue',
  delivery: 'Delivery issue', not_as_described: 'Not as described', no_longer_needed: 'No longer needed', not_delivered: 'Not delivered',
  charged_incorrectly: 'Charged incorrectly', returned_item: 'Item already returned', order_problem: 'Order problem',
  payment_problem: 'Payment problem', delivery_problem: 'Delivery problem', account_problem: 'Account problem',
  follow_up: 'Follow-up on an earlier request', other: 'Other',
};
export const SIMULATED = 'Refunds in this academic demonstration are simulated: no payment provider is contacted and no real money is transferred.';
const REASONS = {
  not_delivered: 'not delivered yet', window_passed: 'return window has ended', window_unknown: 'no return window in the policy',
  not_paid: 'no completed payment', order_required: 'choose an order',
};
const when = (iso) => (iso ? new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '');
const NEEDS_ORDER = { return: true, refund: true };

function SignInFirst({ next }) {
  return (
    <div className="empty">
      <h1>Customer care</h1>
      <p>Please sign in to send or follow a request.</p>
      <Link className="btn btn-primary" to={`/account?next=${encodeURIComponent(next)}`}>Sign in</Link>
    </div>
  );
}

// ---- list ---------------------------------------------------------------------------------------------------------------
export function CareRequestsPage() {
  const { api, session } = useStore();
  const [state, setState] = useState({ loading: true, requests: [], error: null });
  useEffect(() => {
    if (!session || session.customer.role !== 'customer') return;
    api.careRequests().then((d) => setState({ loading: false, requests: d.requests, error: null }),
      (e) => setState({ loading: false, requests: [], error: e.message }));
  }, [api, session]);
  if (!session) return <SignInFirst next="/support/requests" />;
  if (session.customer.role !== 'customer') return <p className="empty">Staff: see <Link to="/staff/care">Customer care</Link>.</p>;
  return (
    <section className="page-section care-page" aria-labelledby="care-title">
      <div className="page-head"><h1 id="care-title">My requests</h1><Link to="/account" className="back-link">← Your account</Link></div>
      <nav className="care-new" aria-label="Start a new request">
        {Object.entries(KIND_LABELS).map(([k, label]) => <Link key={k} className="btn" to={`/support/new?kind=${k}`}>{label}</Link>)}
      </nav>
      {state.error && <p className="notice notice-error" role="alert">{state.error}</p>}
      {state.loading ? <p className="muted" aria-live="polite">Loading your requests…</p> : state.requests.length === 0 ? (
        <p className="empty">You haven’t sent any requests yet.</p>
      ) : (
        <ul className="care-list">
          {state.requests.map((r) => (
            <li key={r.reference} className="card care-item">
              <div>
                <Link to={`/support/requests/${r.reference}`} className="care-ref">{r.reference}</Link>
                <span className="muted"> · {KIND_NAMES[r.kind]}{r.order_number ? ` · order ${r.order_number}` : ''}</span>
                <p className="care-desc">{CATEGORY_LABELS[r.category] || r.category}: {r.description}</p>
              </div>
              <span className={`status care-status care-${r.status}`}>{r.status_label}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ---- new request ------------------------------------------------------------------------------------------------------------
export function CareNewPage() {
  const { api, session, config } = useStore();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const kind = KIND_LABELS[params.get('kind')] ? params.get('kind') : 'complaint';
  const [order, setOrder] = useState(params.get('order') || '');
  const [orders, setOrders] = useState(null);
  const [detail, setDetail] = useState(null);
  const [form, setForm] = useState({ item: '', category: '', description: '' });
  const [step, setStep] = useState('form');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const key = useRef(newIdempotencyKey());

  useEffect(() => {
    if (!session || session.customer.role !== 'customer') return;
    setOrders(null);
    api.careOptions(kind).then((d) => setOrders(d), (e) => setError(e.message));
  }, [api, session, kind]);
  useEffect(() => {
    setDetail(null);
    setForm((f) => ({ ...f, item: '' }));
    if (!order || !session || session.customer.role !== 'customer') return;
    api.careOptions(kind, order).then(setDetail, (e) => setError(e.message));
  }, [api, session, kind, order]);

  if (!session) return <SignInFirst next={`/support/new?kind=${kind}`} />;
  if (session.customer.role !== 'customer') return <p className="empty">Staff accounts can’t send customer requests.</p>;
  if (!orders) return error ? <p className="notice notice-error" role="alert">{error}</p> : <p className="muted" aria-live="polite">Loading…</p>;

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const eligibleNow = !order || detail?.order?.eligible;
  const items = detail?.items || [];
  const needItem = kind === 'return' && items.length > 1;
  const chosenItem = items.find((i) => String(i.id) === form.item);
  const canReview = (!NEEDS_ORDER[kind] || order) && eligibleNow && form.category && form.description.trim() && (!needItem || form.item);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const body = { kind, category: form.category, description: form.description.trim(),
        ...(order ? { order_number: order } : {}), ...(form.item ? { item_id: Number(form.item) } : {}) };
      const r = await api.careCreate(body, key.current);
      navigate(`/support/requests/${r.request.reference}`, { replace: true, state: { created: true } });
    } catch (e) {
      setError(e.message);
      if (e.status === 409 || e.status === 422) { key.current = newIdempotencyKey(); setStep('form'); }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page-section care-page" aria-labelledby="care-new-title">
      <div className="page-head"><h1 id="care-new-title">{KIND_LABELS[kind]}</h1><Link to="/support/requests" className="back-link">← My requests</Link></div>
      {kind === 'refund' && <p className="notice notice-info" role="note">{SIMULATED}</p>}
      {kind === 'escalation' && (
        <p className="notice notice-info" role="note">Your request is recorded for the {config.name} team to review. Nobody is available live
          here; replies appear on the request page.</p>
      )}
      {step === 'form' ? (
        <form className="card care-form" onSubmit={(e) => { e.preventDefault(); if (canReview) setStep('review'); }} noValidate>
          <label htmlFor="care-order">Order{NEEDS_ORDER[kind] ? '' : ' (optional)'}</label>
          <select id="care-order" value={order} onChange={(e) => setOrder(e.target.value)} required={!!NEEDS_ORDER[kind]}>
            <option value="">{NEEDS_ORDER[kind] ? 'Choose an order…' : 'Not about an order'}</option>
            {orders.orders.map((o) => (
              <option key={o.order_number} value={o.order_number} disabled={!o.eligible}>
                {o.order_number}{o.eligible ? '' : ` — ${REASONS[o.reason] || 'not eligible'}`}
              </option>
            ))}
          </select>
          {NEEDS_ORDER[kind] && orders.orders.every((o) => !o.eligible) && (
            <p className="notice notice-warn" role="status">
              None of your orders can have a {KIND_NAMES[kind].toLowerCase()} right now. You can <Link to="/support/new?kind=complaint">report a problem</Link> or{' '}
              <Link to="/support/new?kind=escalation">ask for human help</Link> instead.
            </p>
          )}
          {detail && !detail.order.eligible && (
            <p className="notice notice-warn" role="status">This order isn’t eligible: {REASONS[detail.order.reason] || detail.order.reason}
              {detail.order.until ? ` (${detail.order.until})` : ''}.</p>
          )}
          {kind === 'return' && detail?.order?.eligible && detail.order.until && (
            <p className="field-help">Under the store’s {detail.order.days}-day returns policy, a return can be requested until {detail.order.until}.</p>
          )}
          {items.length > 0 && kind !== 'escalation' && kind !== 'refund' && (
            <>
              <label htmlFor="care-item">Item{needItem ? '' : ' (optional)'}</label>
              <select id="care-item" value={form.item} onChange={set('item')} required={needItem}>
                <option value="">{needItem ? 'Choose an item…' : 'The whole order'}</option>
                {items.map((i) => (
                  <option key={i.id} value={i.id} disabled={!!i.open_request}>
                    {i.name} × {i.quantity}{i.open_request ? ` — already open: ${i.open_request}` : ''}
                  </option>
                ))}
              </select>
            </>
          )}
          <label htmlFor="care-category">Reason</label>
          <select id="care-category" value={form.category} onChange={set('category')} required>
            <option value="">Choose a reason…</option>
            {orders.categories.map((c) => <option key={c} value={c}>{CATEGORY_LABELS[c] || c}</option>)}
          </select>
          <label htmlFor="care-description">Describe it in your own words</label>
          <textarea id="care-description" rows={4} maxLength={1000} required value={form.description} onChange={set('description')}
            aria-describedby="care-description-help" />
          <p id="care-description-help" className="field-help">Never include card numbers, CVV, UPI PIN or passwords — they are never needed.</p>
          {error && <p className="notice notice-error" role="alert">{error}</p>}
          <button type="submit" className="btn btn-primary" disabled={!canReview}>Review</button>
        </form>
      ) : (
        <div className="card care-review">
          <h2>Check before sending</h2>
          <dl className="care-summary">
            <div><dt>Request</dt><dd>{KIND_NAMES[kind]}</dd></div>
            <div><dt>Order</dt><dd>{order || 'Not about an order'}</dd></div>
            {chosenItem && <div><dt>Item</dt><dd>{chosenItem.name}</dd></div>}
            <div><dt>Reason</dt><dd>{CATEGORY_LABELS[form.category]}</dd></div>
            <div><dt>Details</dt><dd>{form.description.trim()}</dd></div>
          </dl>
          {error && <p className="notice notice-error" role="alert">{error}</p>}
          <div className="detail-actions">
            <button type="button" className="btn" onClick={() => setStep('form')} disabled={busy}>Edit</button>
            <button type="button" className="btn btn-primary" onClick={submit} disabled={busy}>{busy ? 'Sending…' : 'Confirm and send'}</button>
          </div>
        </div>
      )}
    </section>
  );
}

// ---- one request ---------------------------------------------------------------------------------------------------------------
export function CareRequestPage() {
  const { ref } = useParams();
  const { api, session } = useStore();
  const [state, setState] = useState({ loading: true, request: null, error: null });
  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirmWithdraw, setConfirmWithdraw] = useState(false);
  const [flash, setFlash] = useState(null);
  const load = useCallback(() => api.careRequest(ref).then((d) => setState({ loading: false, request: d.request, error: null }),
    (e) => setState({ loading: false, request: null, error: e.status === 404 ? 'Request not found on your account.' : e.message })), [api, ref]);
  useEffect(() => { if (session?.customer.role === 'customer') load(); }, [load, session]);

  if (!session) return <SignInFirst next={`/support/requests/${ref}`} />;
  if (state.loading) return <p className="muted" aria-live="polite">Loading {ref}…</p>;
  if (state.error) return <div className="empty"><h1>{ref}</h1><p className="notice notice-error" role="alert">{state.error}</p><Link to="/support/requests">My requests</Link></div>;
  const r = state.request;

  async function act(fn, ok) {
    setBusy(true);
    setFlash(null);
    try {
      const d = await fn();
      setState({ loading: false, request: d.request, error: null });
      setFlash({ ok: true, text: ok });
    } catch (e) {
      setFlash({ ok: false, text: e.message });
    } finally {
      setBusy(false);
      setConfirmWithdraw(false);
    }
  }

  return (
    <article className="page-section care-page" aria-labelledby="care-ref-title">
      <div className="page-head">
        <div>
          <Link to="/support/requests" className="back-link">← My requests</Link>
          <h1 id="care-ref-title">{r.reference}</h1>
          <p className="muted">{KIND_NAMES[r.kind]} · sent {when(r.created_at)}</p>
        </div>
        <span className={`status care-status care-${r.status}`}>{r.status_label}</span>
      </div>
      {r.simulated && <p className="notice notice-info" role="note">{r.simulated_notice}</p>}
      {r.kind === 'escalation' && r.open && <p className="notice notice-info" role="note">Recorded for staff review — this isn’t a live chat; replies appear below.</p>}
      {flash && <p className={`notice ${flash.ok ? 'notice-ok' : 'notice-error'}`} role={flash.ok ? 'status' : 'alert'}>{flash.text}</p>}
      <section className="card">
        <dl className="care-summary">
          {r.order_number && <div><dt>Order</dt><dd><Link to={`/orders/${r.order_number}`}>{r.order_number}</Link></dd></div>}
          {r.item && <div><dt>Item</dt><dd>{r.item.name}</dd></div>}
          <div><dt>Reason</dt><dd>{CATEGORY_LABELS[r.category] || r.category}</dd></div>
          <div><dt>Your message</dt><dd>{r.description}</dd></div>
        </dl>
      </section>
      <section className="card care-updates" aria-labelledby="care-updates-title">
        <h2 id="care-updates-title">Updates</h2>
        <ol>
          {r.updates.map((u, i) => (
            <li key={i}>
              <time dateTime={u.at}>{when(u.at)}</time> — <strong>{u.by === 'you' ? 'You' : u.by === 'staff' ? 'Store team' : 'System'}</strong>
              {u.status_label && <> · <span className={`status care-status care-${u.status}`}>{u.status_label}</span></>}
              {u.message && <p className="care-message">{u.message}</p>}
            </li>
          ))}
        </ol>
      </section>
      {r.can_reply && (
        <form className="card care-form" onSubmit={(e) => { e.preventDefault(); if (reply.trim()) act(() => api.careReply(r.reference, reply.trim()), 'Message sent.').then(() => setReply('')); }}>
          <label htmlFor="care-reply">Send a message to the store team</label>
          <textarea id="care-reply" rows={3} maxLength={1000} value={reply} onChange={(e) => setReply(e.target.value)} />
          <button type="submit" className="btn btn-primary" disabled={busy || !reply.trim()}>Send message</button>
        </form>
      )}
      {r.can_withdraw && (
        confirmWithdraw ? (
          <div className="notice notice-warn" role="group" aria-label={`Confirm withdrawing ${r.reference}`}>
            <p>Withdraw {r.reference}? Staff won’t work on it any more.</p>
            <div className="detail-actions">
              <button type="button" className="btn" onClick={() => setConfirmWithdraw(false)} disabled={busy}>Keep it</button>
              <button type="button" className="btn btn-danger" onClick={() => act(() => api.careWithdraw(r.reference), 'Request withdrawn.')} disabled={busy}>Yes, withdraw</button>
            </div>
          </div>
        ) : <button type="button" className="btn btn-quiet" onClick={() => setConfirmWithdraw(true)}>Withdraw this request</button>
      )}
    </article>
  );
}

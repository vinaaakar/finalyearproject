// Staff fulfilment screens (Phase F). Shown only to agent accounts; every action is authorised and validated again by
// the server (state machine, expected status, input rules), so this UI is a convenience, not the security boundary.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useStore } from '../StoreApp.jsx';

const STATUS_FILTERS = [
  ['to_ship', 'To ship', ['processing']],
  ['in_transit', 'In transit', ['shipped', 'out_for_delivery']],
  ['delivered', 'Delivered', ['delivered']],
  ['unpaid', 'Awaiting payment', ['pending_payment']],
  ['closed', 'Cancelled / returned', ['cancelled', 'returned']],
  ['all', 'All', []],
];
const PAGE = 25;

const when = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '');

export function StaffGate({ children, next = '/staff/orders' }) {
  const { session } = useStore();
  if (!session) {
    return (
      <div className="empty"><h1>Staff sign-in required</h1>
        <Link className="btn btn-primary" to={`/account?next=${next}`}>Sign in</Link></div>
    );
  }
  if (session.customer.role !== 'agent') {
    return <div className="empty"><h1>Staff only</h1><p>This page is for store staff.</p><Link to="/">Back to the shop</Link></div>;
  }
  return children;
}

export function StaffOrdersPage() {
  return <StaffGate><StaffOrders /></StaffGate>;
}

function StaffOrders() {
  const { api } = useStore();
  const [params, setParams] = useSearchParams();
  const filter = STATUS_FILTERS.find(([k]) => k === params.get('filter')) || STATUS_FILTERS[0];
  const q = params.get('q') || '';
  const offset = Math.max(0, Number(params.get('offset')) || 0);
  const [query, setQuery] = useState(q);
  const [state, setState] = useState({ loading: true, orders: [], total: 0, error: null });

  useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    api.staffOrders({ status: filter[2], q, limit: PAGE, offset }).then(
      (d) => live && setState({ loading: false, orders: d.orders, total: d.total, error: null }),
      (e) => live && setState({ loading: false, orders: [], total: 0, error: e.message }),
    );
    return () => { live = false; };
  }, [api, filter, q, offset]);

  const go = (changes) => {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    setParams(next);
  };

  return (
    <section className="staff-page" aria-labelledby="staff-title">
      <h1 id="staff-title">Fulfil orders</h1>
      <div className="chips" role="group" aria-label="Filter orders by status">
        {STATUS_FILTERS.map(([key, label]) => (
          <button key={key} type="button" className={`chip ${filter[0] === key ? 'chip-active' : ''}`} aria-pressed={filter[0] === key}
            onClick={() => go({ filter: key, offset: '' })}>{label}</button>
        ))}
      </div>
      <form className="search staff-search" role="search" onSubmit={(e) => { e.preventDefault(); go({ q: query.trim(), offset: '' }); }}>
        <label htmlFor="staff-q" className="sr-only">Search by order number or customer name</label>
        <input id="staff-q" type="search" value={query} onChange={(e) => setQuery(e.target.value)} maxLength={60}
          placeholder="Order number or customer name" />
        <button type="submit" className="btn">Search</button>
      </form>
      {state.error && <p className="notice notice-error" role="alert">{state.error}</p>}
      {state.loading ? <p className="muted" aria-live="polite">Loading orders…</p> : state.orders.length === 0 ? (
        <p className="empty">No orders match.</p>
      ) : (
        <>
          <p className="muted" aria-live="polite">{state.total} order{state.total === 1 ? '' : 's'}</p>
          <div className="table-scroll">
            <table className="staff-table">
              <caption className="sr-only">Orders, newest first</caption>
              <thead><tr><th scope="col">Order</th><th scope="col">Customer</th><th scope="col">Placed</th><th scope="col">Items</th>
                <th scope="col">Total</th><th scope="col">Status</th></tr></thead>
              <tbody>
                {state.orders.map((o) => (
                  <tr key={o.order_number}>
                    <th scope="row"><Link to={`/staff/orders/${o.order_number}`}>{o.order_number}</Link></th>
                    <td>{o.customer_name}</td>
                    <td>{when(o.placed_at)}</td>
                    <td>{o.item_count}</td>
                    <td>{o.total}</td>
                    <td><span className={`status status-${o.status}`}>{o.status_label}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav className="pager" aria-label="Pages">
            <button type="button" className="btn btn-small" disabled={offset === 0} onClick={() => go({ offset: String(Math.max(0, offset - PAGE)) || '' })}>Previous</button>
            <span className="muted">{offset + 1}–{Math.min(offset + PAGE, state.total)} of {state.total}</span>
            <button type="button" className="btn btn-small" disabled={offset + PAGE >= state.total} onClick={() => go({ offset: String(offset + PAGE) })}>Next</button>
          </nav>
        </>
      )}
    </section>
  );
}

export function StaffOrderPage() {
  return <StaffGate><StaffOrder /></StaffGate>;
}

const ACTION_LABELS = { ship: 'Mark as shipped', out_for_delivery: 'Mark out for delivery', deliver: 'Mark as delivered', return: 'Record a return' };

function StaffOrder() {
  const { number } = useParams();
  const { api } = useStore();
  const [state, setState] = useState({ loading: true, order: null, error: null });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const [form, setForm] = useState({ carrier: '', tracking_number: '', tracking_url: '', estimated_delivery: '', note: '' });
  const headingRef = useRef(null);

  const load = useCallback(() => api.staffOrder(number).then(
    (d) => setState({ loading: false, order: d.order, error: null }),
    (e) => setState({ loading: false, order: null, error: e.status === 404 ? 'Order not found in this store.' : e.message }),
  ), [api, number]);
  useEffect(() => { load(); }, [load]);

  async function act(action, extra = {}) {
    if (busy) return;
    setBusy(true);
    setMessage(null);
    try {
      const path = action === 'out_for_delivery' ? 'out-for-delivery' : action;
      const body = { expected_status: state.order.status, note: form.note.trim() || undefined, ...extra };
      const d = await api.staffAction(number, path, body);
      setState({ loading: false, order: d.order, error: null });
      setForm({ carrier: '', tracking_number: '', tracking_url: '', estimated_delivery: '', note: '' });
      setMessage({ ok: true, text: `Order ${number} is now ${d.order.status_label}.` });
      headingRef.current?.focus();
    } catch (e) {
      const fields = (e.details || []).map((x) => `${x.field}: ${x.issue}`).join('; ');
      setMessage({ ok: false, text: `${e.message}${fields && e.code !== 'stale_status' ? ` (${fields})` : ''}`, stale: e.code === 'stale_status' });
    } finally {
      setBusy(false);
    }
  }

  if (state.loading) return <p className="muted" aria-live="polite">Loading order {number}…</p>;
  if (state.error) return <div className="empty"><h1>Order {number}</h1><p className="notice notice-error" role="alert">{state.error}</p><Link to="/staff/orders">All orders</Link></div>;
  const o = state.order;
  const a = o.shipping_address;
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <article className="staff-page" aria-labelledby="staff-order-title">
      <Link to="/staff/orders" className="back-link">← All orders</Link>
      <div className="page-head">
        <h1 id="staff-order-title" tabIndex={-1} ref={headingRef}>Order {o.order_number}</h1>
        <span className={`status status-${o.status}`}>{o.status_label}</span>
      </div>
      {message && (
        <div className={`notice ${message.ok ? 'notice-ok' : 'notice-error'}`} role={message.ok ? 'status' : 'alert'}>
          {message.text} {message.stale && <button type="button" className="link-btn" onClick={() => { setMessage(null); load(); }}>Reload order</button>}
        </div>
      )}
      <div className="order-detail-grid">
        <section className="card" aria-labelledby="so-items">
          <h2 id="so-items">Items</h2>
          <p className="muted">Customer: {o.customer_name} · placed {when(o.placed_at)}</p>
          <ul className="order-lines">
            {o.items.map((i) => <li key={i.slug}><span>{i.name} × {i.quantity}</span><span>{i.line_total}</span></li>)}
          </ul>
          <p><strong>Total {o.total}</strong>{o.shipping_method && <span className="muted"> · {o.shipping_method} shipping</span>}</p>
        </section>
        <section className="card" aria-labelledby="so-ship">
          <h2 id="so-ship">Ship to</h2>
          {a ? <address className="review-address">{a.name}<br />{a.line1}{a.line2 && <><br />{a.line2}</>}<br />{a.city}, {a.region} {a.postal_code}
            {a.country_name && <><br />{a.country_name}</>}{a.phone && <><br />Phone: {a.phone}</>}</address>
            : <p className="muted">No address stored with this order.</p>}
          {o.tracking_number && <p>{o.carrier} · {o.tracking_url ? <a href={o.tracking_url} target="_blank" rel="noopener noreferrer">{o.tracking_number}</a> : o.tracking_number}</p>}
        </section>
      </div>

      {o.actions.length > 0 ? (
        <section className="card staff-actions" aria-labelledby="so-actions">
          <h2 id="so-actions">Next step</h2>
          {o.actions.includes('ship') && (
            <form onSubmit={(e) => { e.preventDefault(); act('ship', { carrier: form.carrier.trim(), tracking_number: form.tracking_number.trim(),
              tracking_url: form.tracking_url.trim() || undefined, estimated_delivery: form.estimated_delivery || undefined }); }}>
              <div className="form-row">
                <div><label htmlFor="ship-carrier">Carrier</label><input id="ship-carrier" required minLength={2} maxLength={40} value={form.carrier} onChange={set('carrier')} /></div>
                <div><label htmlFor="ship-tracking">Tracking number</label><input id="ship-tracking" required minLength={4} maxLength={40} pattern="[A-Za-z0-9\-]+" value={form.tracking_number} onChange={set('tracking_number')} /></div>
                <div><label htmlFor="ship-eta">Estimated delivery <span className="muted">(optional)</span></label><input id="ship-eta" type="date" value={form.estimated_delivery} onChange={set('estimated_delivery')} /></div>
              </div>
              <label htmlFor="ship-url">Tracking link <span className="muted">(optional, https://)</span></label>
              <input id="ship-url" type="url" pattern="https://.+" maxLength={300} value={form.tracking_url} onChange={set('tracking_url')} />
              <label htmlFor="ship-note">Note for the order history <span className="muted">(optional, staff only)</span></label>
              <input id="ship-note" maxLength={500} value={form.note} onChange={set('note')} />
              <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : ACTION_LABELS.ship}</button>
            </form>
          )}
          {o.actions.some((x) => x !== 'ship') && (
            <div className="staff-buttons">
              {o.actions.filter((x) => x !== 'ship' && x !== 'return').map((x) => (
                <button key={x} type="button" className="btn btn-primary" disabled={busy} onClick={() => act(x)}>{ACTION_LABELS[x]}</button>
              ))}
              {o.actions.includes('return') && (
                <form className="staff-return" onSubmit={(e) => { e.preventDefault(); act('return', { note: form.note.trim() }); }}>
                  <label htmlFor="return-note">Return reason (required)</label>
                  <input id="return-note" required minLength={3} maxLength={500} value={form.note} onChange={set('note')} />
                  <button type="submit" className="btn" disabled={busy}>{ACTION_LABELS.return}</button>
                </form>
              )}
            </div>
          )}
        </section>
      ) : <p className="muted">No fulfilment step is available for an order that is {o.status_label}.</p>}

      <section className="card order-history" aria-labelledby="so-history">
        <h2 id="so-history">History</h2>
        {o.history.length === 0 ? <p className="muted">No changes have been recorded for this order (it predates status history).</p> : (
          <ol>
            {o.history.map((h, i) => (
              <li key={i}>
                <time dateTime={h.at}>{when(h.at)}</time> — {h.from_status === h.status ? 'tracking updated' : <span className={`status status-${h.status}`}>{h.status_label}</span>}
                {' '}by {h.actor_name}{h.actor_role === 'agent' ? ' (staff)' : h.actor_role === 'customer' ? ' (customer)' : ''}
                {h.carrier && <> · {h.carrier} {h.tracking_number}</>}
                {h.note && <span className="muted"> — {h.note}</span>}
              </li>
            ))}
          </ol>
        )}
      </section>
    </article>
  );
}

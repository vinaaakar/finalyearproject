// Staff customer-care screens: queues for complaints, return requests, SIMULATED refund requests and human-help requests,
// and one request with its order, history, assignment, internal notes, customer messages and decisions. Only agent
// accounts of THIS store see them; the server authorises and validates every action (allowed status changes, the status
// the screen was showing, reasons for rejections) — this UI is a convenience, not the security boundary.
import React, { useCallback, useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useStore } from '../StoreApp.jsx';
import { StaffGate } from './StaffPages.jsx';
import { CATEGORY_LABELS, KIND_NAMES, SIMULATED } from './CarePages.jsx';

const QUEUES = [['complaint', 'Complaints'], ['return', 'Returns'], ['refund', 'Refunds (simulated)'], ['escalation', 'Human help'], ['', 'All']];
const STATUS_GROUPS = [['open', 'Open', ['open', 'requested', 'under_review', 'awaiting_customer', 'assigned', 'in_progress', 'approved', 'received', 'inspected']],
  ['closed', 'Closed', ['rejected', 'completed', 'simulated_completed', 'resolved', 'closed', 'withdrawn']], ['all', 'All', []]];
const ACTION_LABELS = {
  under_review: 'Start review', awaiting_customer: 'Ask the customer', resolved: 'Mark resolved', rejected: 'Reject', closed: 'Close',
  approved: 'Approve', received: 'Record item received', inspected: 'Record item inspected', completed: 'Complete return',
  simulated_completed: 'Mark refund completed (simulated)', assigned: 'Mark assigned', in_progress: 'Mark in progress',
};
const PAGE = 25;
const when = (iso) => (iso ? new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '');

export function StaffCarePage() {
  return <StaffGate next="/staff/care"><StaffCareQueue /></StaffGate>;
}

function StaffCareQueue() {
  const { api } = useStore();
  const [params, setParams] = useSearchParams();
  const kind = QUEUES.find(([k]) => k === (params.get('kind') ?? 'complaint')) || QUEUES[0];
  const group = STATUS_GROUPS.find(([k]) => k === params.get('status')) || STATUS_GROUPS[0];
  const q = params.get('q') || '';
  const from = params.get('from') || '';
  const to = params.get('to') || '';
  const offset = Math.max(0, Number(params.get('offset')) || 0);
  const [query, setQuery] = useState(q);
  const [state, setState] = useState({ loading: true, rows: [], total: 0, error: null });

  useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    api.staffCare({ kind: kind[0] ? [kind[0]] : [], status: group[2], q, dateFrom: from, dateTo: to, limit: PAGE, offset }).then(
      (d) => live && setState({ loading: false, rows: d.requests, total: d.total, error: null }),
      (e) => live && setState({ loading: false, rows: [], total: 0, error: e.message }));
    return () => { live = false; };
  }, [api, kind, group, q, from, to, offset]);

  const go = (changes) => {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([k, v]) => (v !== '' && v != null ? next.set(k, v) : next.delete(k)));
    setParams(next);
  };

  return (
    <section className="staff-page" aria-labelledby="care-staff-title">
      <h1 id="care-staff-title">Customer care</h1>
      <div className="chips" role="group" aria-label="Request type">
        {QUEUES.map(([k, label]) => (
          <button key={label} type="button" className={`chip ${kind[0] === k ? 'chip-active' : ''}`} aria-pressed={kind[0] === k}
            onClick={() => go({ kind: k, offset: '' })}>{label}</button>
        ))}
      </div>
      <div className="chips" role="group" aria-label="Status">
        {STATUS_GROUPS.map(([k, label]) => (
          <button key={k} type="button" className={`chip ${group[0] === k ? 'chip-active' : ''}`} aria-pressed={group[0] === k}
            onClick={() => go({ status: k, offset: '' })}>{label}</button>
        ))}
      </div>
      <form className="search staff-search care-filters" role="search" onSubmit={(e) => { e.preventDefault(); go({ q: query.trim(), offset: '' }); }}>
        <label htmlFor="care-q" className="sr-only">Search by request or order reference</label>
        <input id="care-q" type="search" value={query} onChange={(e) => setQuery(e.target.value)} maxLength={30} placeholder="Request or order reference" />
        <label htmlFor="care-from">From</label>
        <input id="care-from" type="date" value={from} onChange={(e) => go({ from: e.target.value, offset: '' })} />
        <label htmlFor="care-to">To</label>
        <input id="care-to" type="date" value={to} onChange={(e) => go({ to: e.target.value, offset: '' })} />
        <button type="submit" className="btn">Search</button>
      </form>
      {kind[0] === 'refund' && <p className="notice notice-info" role="note">{SIMULATED}</p>}
      {state.error && <p className="notice notice-error" role="alert">{state.error}</p>}
      {state.loading ? <p className="muted" aria-live="polite">Loading requests…</p> : state.rows.length === 0 ? (
        <p className="empty">No requests match.</p>
      ) : (
        <>
          <p className="muted" aria-live="polite">{state.total} request{state.total === 1 ? '' : 's'}</p>
          <div className="table-scroll">
            <table className="staff-table">
              <caption className="sr-only">Customer-care requests, open first, newest first</caption>
              <thead><tr><th scope="col">Request</th><th scope="col">Type</th><th scope="col">Customer</th><th scope="col">Order</th>
                <th scope="col">Reason</th><th scope="col">Sent</th><th scope="col">Assigned</th><th scope="col">Status</th></tr></thead>
              <tbody>
                {state.rows.map((r) => (
                  <tr key={r.reference}>
                    <th scope="row"><Link to={`/staff/care/${r.reference}`}>{r.reference}</Link></th>
                    <td>{KIND_NAMES[r.kind]}</td>
                    <td>{r.customer_name}</td>
                    <td>{r.order_number || '—'}</td>
                    <td>{CATEGORY_LABELS[r.category] || r.category}</td>
                    <td>{when(r.created_at)}</td>
                    <td>{r.assigned_to || '—'}</td>
                    <td><span className={`status care-status care-${r.status}`}>{r.status_label}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav className="pager" aria-label="Pages">
            <button type="button" className="btn btn-small" disabled={offset === 0} onClick={() => go({ offset: String(Math.max(0, offset - PAGE)) })}>Previous</button>
            <span className="muted">{offset + 1}–{Math.min(offset + PAGE, state.total)} of {state.total}</span>
            <button type="button" className="btn btn-small" disabled={offset + PAGE >= state.total} onClick={() => go({ offset: String(offset + PAGE) })}>Next</button>
          </nav>
        </>
      )}
    </section>
  );
}

export function StaffCareRequestPage() {
  return <StaffGate next="/staff/care"><StaffCareRequest /></StaffGate>;
}

function StaffCareRequest() {
  const { ref } = useParams();
  const { api } = useStore();
  const [state, setState] = useState({ loading: true, request: null, error: null });
  const [agents, setAgents] = useState([]);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState(null);
  const [decision, setDecision] = useState({ status: '', message: '', note: '' });
  const [note, setNote] = useState('');
  const [message, setMessage] = useState('');

  const load = useCallback(() => api.staffCareRequest(ref).then((d) => setState({ loading: false, request: d.request, error: null }),
    (e) => setState({ loading: false, request: null, error: e.status === 404 ? 'Request not found in this store.' : e.message })), [api, ref]);
  useEffect(() => { load(); api.staffCareAgents().then((d) => setAgents(d.agents), () => {}); }, [load, api]);

  if (state.loading) return <p className="muted" aria-live="polite">Loading {ref}…</p>;
  if (state.error) return <div className="empty"><h1>{ref}</h1><p className="notice notice-error" role="alert">{state.error}</p><Link to="/staff/care">Back to customer care</Link></div>;
  const r = state.request;
  const needsReason = r.reason_required_for.includes(decision.status);

  async function act(fn, ok) {
    setBusy(true);
    setFlash(null);
    try {
      const d = await fn();
      setState({ loading: false, request: d.request, error: null });
      setFlash({ ok: true, text: ok });
      return true;
    } catch (e) {
      setFlash({ ok: false, text: e.message, stale: e.code === 'stale_status' });
      return false;
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="staff-page care-page" aria-labelledby="care-staff-ref">
      <div className="page-head">
        <div>
          <Link to={`/staff/care?kind=${r.kind}`} className="back-link">← Customer care</Link>
          <h1 id="care-staff-ref">{r.reference}</h1>
          <p className="muted">{KIND_NAMES[r.kind]} · {CATEGORY_LABELS[r.category] || r.category} · sent {when(r.created_at)}</p>
        </div>
        <span className={`status care-status care-${r.status}`}>{r.status_label}</span>
      </div>
      {r.simulated && <p className="notice notice-info" role="note">{SIMULATED}</p>}
      {flash && (
        <p className={`notice ${flash.ok ? 'notice-ok' : 'notice-error'}`} role={flash.ok ? 'status' : 'alert'}>
          {flash.text}{flash.stale && <> <button type="button" className="btn btn-small" onClick={load}>Reload</button></>}
        </p>
      )}
      <div className="order-detail-grid">
        <section className="card" aria-labelledby="care-customer-title">
          <h2 id="care-customer-title">Customer and request</h2>
          <dl className="care-summary">
            <div><dt>Customer</dt><dd>{r.customer.name} · {r.customer.email}</dd></div>
            {r.item && <div><dt>Item</dt><dd>{r.item.name} × {r.item.quantity}</dd></div>}
            <div><dt>Customer’s message</dt><dd>{r.description}</dd></div>
            <div><dt>Assigned to</dt><dd>{r.assigned_to?.name || 'Nobody yet'}</dd></div>
          </dl>
          {r.open && agents.length > 0 && (
            <form className="care-inline" onSubmit={(e) => { e.preventDefault(); const id = Number(e.target.elements.assignee.value); if (id) act(() => api.staffCareAssign(r.reference, id), 'Assigned.'); }}>
              <label htmlFor="care-assignee">Assign to</label>
              <select id="care-assignee" name="assignee" defaultValue={r.assigned_to?.id || ''}>
                <option value="">Choose staff…</option>
                {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
              <button type="submit" className="btn btn-small" disabled={busy}>Assign</button>
            </form>
          )}
        </section>
        <section className="card" aria-labelledby="care-order-title">
          <h2 id="care-order-title">Order</h2>
          {r.order ? (
            <dl className="care-summary">
              <div><dt>Order</dt><dd><Link to={`/staff/orders/${r.order.order_number}`}>{r.order.order_number}</Link> · {r.order.status.replace(/_/g, ' ')}</dd></div>
              <div><dt>Total</dt><dd>{r.order.total}</dd></div>
              <div><dt>Payment</dt><dd>{r.order.payment ? `${r.order.payment.status} · ${r.order.payment.amount} (sandbox)` : 'none recorded'}</dd></div>
              {r.order.delivered_at && <div><dt>Delivered</dt><dd>{when(r.order.delivered_at)}</dd></div>}
              {r.order.return_eligibility && (
                <div><dt>Return window</dt><dd>{r.order.return_eligibility.eligible ? `open until ${r.order.return_eligibility.until}` : `not eligible (${r.order.return_eligibility.reason})`}</dd></div>
              )}
            </dl>
          ) : <p className="muted">Not about an order.</p>}
        </section>
      </div>

      {r.actions.length > 0 && (
        <form className="card care-form" aria-labelledby="care-decide-title"
          onSubmit={async (e) => { e.preventDefault(); if (await act(() => api.staffCareStatus(r.reference, { status: decision.status, expected_status: r.status,
            ...(decision.message.trim() ? { message: decision.message.trim() } : {}), ...(decision.note.trim() ? { note: decision.note.trim() } : {}) }), 'Status updated.')) setDecision({ status: '', message: '', note: '' }); }}>
          <h2 id="care-decide-title">Update status</h2>
          <fieldset className="ship-methods">
            <legend>Next step</legend>
            {r.actions.map((a) => (
              <label key={a} className="radio">
                <input type="radio" name="care-next" value={a} checked={decision.status === a} onChange={() => setDecision((d) => ({ ...d, status: a }))} />
                {ACTION_LABELS[a] || a}
              </label>
            ))}
          </fieldset>
          <label htmlFor="care-decision-message">Message to the customer{needsReason ? ' (required: the reason)' : ' (optional)'}</label>
          <textarea id="care-decision-message" rows={2} maxLength={1000} value={decision.message} onChange={(e) => setDecision((d) => ({ ...d, message: e.target.value }))} />
          <label htmlFor="care-decision-note">Internal note (staff only, optional)</label>
          <textarea id="care-decision-note" rows={2} maxLength={1000} value={decision.note} onChange={(e) => setDecision((d) => ({ ...d, note: e.target.value }))} />
          <button type="submit" className="btn btn-primary" disabled={busy || !decision.status || (needsReason && !decision.message.trim())}>Save</button>
        </form>
      )}

      <div className="order-detail-grid">
        <form className="card care-form" onSubmit={async (e) => { e.preventDefault(); if (message.trim() && await act(() => api.staffCareMessage(r.reference, message.trim()), 'Message sent to the customer.')) setMessage(''); }}>
          <label htmlFor="care-message">Message to the customer</label>
          <textarea id="care-message" rows={3} maxLength={1000} value={message} onChange={(e) => setMessage(e.target.value)} />
          <button type="submit" className="btn" disabled={busy || !message.trim()}>Send to customer</button>
        </form>
        <form className="card care-form" onSubmit={async (e) => { e.preventDefault(); if (note.trim() && await act(() => api.staffCareNote(r.reference, note.trim()), 'Internal note added.')) setNote(''); }}>
          <label htmlFor="care-note">Internal note (never shown to the customer)</label>
          <textarea id="care-note" rows={3} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />
          <button type="submit" className="btn" disabled={busy || !note.trim()}>Add note</button>
        </form>
      </div>

      <section className="card care-updates" aria-labelledby="care-history-title">
        <h2 id="care-history-title">History</h2>
        <ol>
          {r.history.map((h, i) => (
            <li key={i} className={h.visibility === 'internal' ? 'care-internal' : undefined}>
              <time dateTime={h.at}>{when(h.at)}</time> — <strong>{h.by}</strong>
              {h.visibility === 'internal' && <span className="badge"> internal</span>}
              {h.to_status && <> · {h.from_status ? `${h.from_status.replace(/_/g, ' ')} → ` : ''}{h.to_status.replace(/_/g, ' ')}</>}
              {h.event === 'assigned' || h.event === 'note' || h.event === 'message' || h.event === 'customer_reply' ? <> · {h.event.replace('_', ' ')}</> : null}
              {h.body && <p className="care-message">{h.body}</p>}
            </li>
          ))}
        </ol>
      </section>
    </article>
  );
}

import React, { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useStore } from '../StoreApp.jsx';

// The normal path of an order; cancelled and returned orders leave it (shown as a notice instead).
const PROGRESS = [
  ['pending_payment', 'Order placed'],
  ['processing', 'Being prepared'],
  ['shipped', 'Shipped'],
  ['out_for_delivery', 'Out for delivery'],
  ['delivered', 'Delivered'],
];

const formatDate = (iso, withTime = false) => {
  if (!iso) return null;
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, withTime
    ? { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }
    : { year: 'numeric', month: 'short', day: 'numeric' });
};

function Progress({ status }) {
  const index = PROGRESS.findIndex(([s]) => s === status);
  if (index < 0) return null;
  return (
    <ol className="order-progress" aria-label="Order progress">
      {PROGRESS.map(([s, label], i) => (
        <li key={s} className={i < index ? 'done' : i === index ? 'current' : ''} aria-current={i === index ? 'step' : undefined}>
          <span className="order-progress-dot" aria-hidden="true">{i < index ? '✓' : ''}</span>
          <span>{label}</span>
          {i < index && <span className="sr-only"> (completed)</span>}
        </li>
      ))}
    </ol>
  );
}

export default function OrderDetailPage() {
  const { number } = useParams();
  const { api, session, config } = useStore();
  const [state, setState] = useState({ loading: true, order: null, error: null, notFound: false });

  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    api.order(number).then(
      (d) => setState({ loading: false, order: d.order, error: null, notFound: false }),
      (e) => setState({ loading: false, order: null, error: e.status === 404 ? null : e.message, notFound: e.status === 404 }),
    );
  }, [api, number]);

  useEffect(() => {
    if (session) load();
  }, [session, load]);

  if (!session) {
    return (
      <div className="empty">
        <h1>Order {number}</h1>
        <p>Please sign in to see this order.</p>
        <Link className="btn btn-primary" to={`/account?next=/orders/${encodeURIComponent(number)}`}>Sign in</Link>
      </div>
    );
  }
  if (state.loading) return <p className="muted" aria-live="polite">Loading order {number}…</p>;
  if (state.notFound) {
    return (
      <div className="empty">
        <h1>Order not found</h1>
        <p>We couldn’t find order {number} in your account. Check the order number, or see all your orders.</p>
        <Link className="btn btn-primary" to="/account">Your orders</Link>
      </div>
    );
  }
  if (state.error) {
    return (
      <div className="empty">
        <h1>Order {number}</h1>
        <p className="notice notice-error" role="alert">{state.error}</p>
        <button type="button" className="btn" onClick={load}>Try again</button>
      </div>
    );
  }

  const o = state.order;
  const a = o.shipping_address;
  const isAgent = session.customer.role === 'agent';
  return (
    <article className="order-detail" aria-labelledby="order-title">
      <div className="page-head">
        <div>
          <Link to="/account" className="back-link">← {isAgent ? 'Store orders' : 'Your orders'}</Link>
          <h1 id="order-title">Order {o.order_number}</h1>
          <p className="muted">Placed {formatDate(o.placed_at, true)}</p>
        </div>
        <span className={`status status-${o.status}`}>{o.status_label}</span>
      </div>

      <Progress status={o.status} />
      {o.status === 'cancelled' && <p className="notice notice-warn">This order was cancelled.</p>}
      {o.status === 'returned' && (
        <p className="notice notice-info">This order has been marked as returned. Refunds are handled by the {config.name} team; this page can’t show refund status.</p>
      )}
      {o.awaiting_payment && (
        <div className="notice notice-warn order-pay">
          <span>This order is waiting for payment.</span>
          <Link className="btn btn-primary btn-small" to={`/orders/${o.order_number}/pay`}>Pay now</Link>
        </div>
      )}

      <div className="order-detail-grid">
        <section className="card" aria-labelledby="items-title">
          <h2 id="items-title">Items</h2>
          <ul className="order-lines">
            {o.items.map((i) => (
              <li key={i.slug}>
                <span><Link to={`/products/${i.slug}`}>{i.name}</Link> <span className="muted">× {i.quantity}</span></span>
                <span>{i.line_total || ''}</span>
              </li>
            ))}
          </ul>
          <dl className="totals">
            {o.subtotal && <div><dt>Subtotal</dt><dd>{o.subtotal}</dd></div>}
            {o.shipping && <div><dt>Shipping{o.shipping_method ? ` (${o.shipping_method})` : ''}</dt><dd>{o.shipping}</dd></div>}
            <div className="totals-total"><dt>Total</dt><dd>{o.total}</dd></div>
          </dl>
        </section>

        <section className="card" aria-labelledby="delivery-title">
          <h2 id="delivery-title">Delivery</h2>
          {a ? (
            <address className="review-address">
              {a.name}<br />{a.line1}{a.line2 && <><br />{a.line2}</>}<br />{a.city}, {a.region} {a.postal_code}
              {a.country_name && <><br />{a.country_name}</>}{a.phone && <><br /><span className="muted">Phone: </span>{a.phone}</>}
            </address>
          ) : <p className="muted">No delivery address is stored with this order.</p>}
          {o.carrier || o.tracking_number ? (
            <p>
              {o.carrier}{o.carrier && o.tracking_number ? ' · ' : ''}
              {o.tracking_url
                ? <a href={o.tracking_url} target="_blank" rel="noopener noreferrer">Track {o.tracking_number}<span className="sr-only"> (opens the carrier’s site in a new tab)</span></a>
                : o.tracking_number}
            </p>
          ) : <p className="muted">Tracking details appear here once the order ships.</p>}
          {o.estimated_delivery && ['processing', 'shipped', 'out_for_delivery'].includes(o.status) && (
            <p>Estimated delivery: {formatDate(o.estimated_delivery)}</p>
          )}
        </section>
      </div>

      {o.history?.length > 0 && (
        <section className="card order-history" aria-labelledby="history-title">
          <h2 id="history-title">Status updates</h2>
          <ol>
            {o.history.map((h, i) => (
              <li key={i}><span className={`status status-${h.status}`}>{h.status_label}</span> <time dateTime={h.at}>{formatDate(h.at, true)}</time>
                {h.note && <span className="muted"> — {h.note}</span>}</li>
            ))}
          </ol>
        </section>
      )}

      {!isAgent && (
        <nav className="card care-order-help" aria-label="Help with this order">
          <h2>Need help with this order?</h2>
          <div className="detail-actions">
            <Link className="btn" to={`/support/new?kind=complaint&order=${o.order_number}`}>Report a problem</Link>
            <Link className="btn" to={`/support/new?kind=return&order=${o.order_number}`}>Return an item</Link>
            <Link className="btn" to={`/support/new?kind=refund&order=${o.order_number}`}>Request a refund</Link>
            <Link className="btn" to={`/support/new?kind=escalation&order=${o.order_number}`}>Get human help</Link>
          </div>
          <p className="field-help">Requests are reviewed by the {config.name} team; you can follow them under <Link to="/support/requests">My requests</Link>.
            Refunds are simulated in this demo.</p>
        </nav>
      )}

      <p className="order-help">
        Questions about this order? Ask {config.assistantName} in the chat, see <Link to="/shipping">shipping</Link> and{' '}
        <Link to="/returns">returns</Link>, or <Link to="/contact">contact us</Link>.
      </p>
    </article>
  );
}

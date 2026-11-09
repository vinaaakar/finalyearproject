import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { newIdempotencyKey } from '../api.js';
import { useStore } from '../StoreApp.jsx';
import { CartSummary } from './CartPage.jsx';
import { ErrorNotice } from './AuthPages.jsx';
import ProductImage from '../components/ProductImage.jsx';

const STATES = 'AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split(' ');
const EMPTY = { full_name: '', line1: '', line2: '', city: '', region: '', postal_code: '' };

export default function CheckoutPage() {
  const { api, session, config } = useStore();
  const navigate = useNavigate();
  const [step, setStep] = useState('shipping');
  const [address, setAddress] = useState(() => ({ ...EMPTY, full_name: session?.customer.name || '' }));
  const [method, setMethod] = useState('standard');
  const [quote, setQuote] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  // One key per review: resubmitting (double click, retry after a network error) cannot create a second order.
  const idemKey = useRef(newIdempotencyKey());
  const set = (k) => (e) => setAddress((a) => ({ ...a, [k]: e.target.value }));

  useEffect(() => {
    if (!session) return;
    api.quote(method).then(setQuote, (e) => setError(e));
  }, [api, session, method]);

  if (!session) {
    return (
      <div className="card form">
        <h1>Checkout</h1>
        <p>Please sign in to check out. Your cart is kept.</p>
        <Link className="btn btn-primary" to="/account?next=/checkout">Sign in</Link>
        <p className="form-links">New here? <Link to="/register?next=/checkout">Create an account</Link></p>
      </div>
    );
  }
  if (session.customer.role === 'agent') return <p className="empty">Staff accounts can’t place orders.</p>;
  if (!quote) return error ? <ErrorNotice error={error} /> : <p className="muted" aria-live="polite">Loading…</p>;
  if (quote.items.length === 0) return <div className="empty"><p>Your cart is empty.</p><Link className="btn" to="/">Continue shopping</Link></div>;

  function toReview(e) {
    e.preventDefault();
    setError(null);
    idemKey.current = newIdempotencyKey();
    setStep('review');
  }

  async function placeOrder() {
    setBusy(true);
    setError(null);
    try {
      const shipping = { ...address, line2: address.line2.trim() || null };
      const r = await api.checkout({ shipping, shippingMethod: method, expectedTotalCents: quote.total_cents, idempotencyKey: idemKey.current });
      navigate(`/orders/${r.order.order_number}/pay`, { replace: true });
    } catch (e) {
      setError(e);
      if (e.status === 409 || e.status === 422) {
        // Prices, stock or the address changed/failed: show the server's current numbers and let the customer re-review.
        api.quote(method).then(setQuote, () => {});
        idemKey.current = newIdempotencyKey();
      }
      if (e.status === 422) setStep('shipping');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page-section">
      <div className="page-head">
        <h1>Checkout</h1>
        <Link to="/cart" className="back-link">← Back to cart</Link>
      </div>
      <ol className="steps" aria-label="Checkout steps">
        <li aria-current={step === 'shipping' ? 'step' : undefined}>1. Shipping</li>
        <li aria-current={step === 'review' ? 'step' : undefined}>2. Review</li>
        <li>3. Payment</li>
      </ol>
      <div className="cart-layout">
        <div>
          {step === 'shipping' ? (
            <form className="card checkout-form" onSubmit={toReview}>
              <h2>Shipping address</h2>
              <label htmlFor="ship-name">Full name</label>
              <input id="ship-name" autoComplete="shipping name" required maxLength={100} value={address.full_name} onChange={set('full_name')} />
              <label htmlFor="ship-line1">Address</label>
              <input id="ship-line1" autoComplete="shipping address-line1" required maxLength={120} value={address.line1} onChange={set('line1')} />
              <label htmlFor="ship-line2">Apartment, suite, etc. (optional)</label>
              <input id="ship-line2" autoComplete="shipping address-line2" maxLength={120} value={address.line2} onChange={set('line2')} />
              <div className="form-row">
                <div>
                  <label htmlFor="ship-city">City</label>
                  <input id="ship-city" autoComplete="shipping address-level2" required maxLength={80} value={address.city} onChange={set('city')} />
                </div>
                <div>
                  <label htmlFor="ship-region">State</label>
                  <select id="ship-region" autoComplete="shipping address-level1" required value={address.region} onChange={set('region')}>
                    <option value="">Select…</option>
                    {STATES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label htmlFor="ship-zip">ZIP code</label>
                  <input id="ship-zip" autoComplete="shipping postal-code" inputMode="numeric" required pattern="\d{5}(-\d{4})?"
                    title="5-digit ZIP code" maxLength={10} value={address.postal_code} onChange={set('postal_code')} />
                </div>
              </div>
              <p className="field-help">United States addresses only.</p>
              <fieldset className="ship-methods">
                <legend>Shipping method</legend>
                {quote.shipping_options.map((o) => (
                  <label key={o.method} className="radio">
                    <input type="radio" name="ship-method" value={o.method} checked={method === o.method} onChange={() => setMethod(o.method)} />
                    {o.label} — {o.cents === 0 ? 'Free' : o.price}
                  </label>
                ))}
              </fieldset>
              <ErrorNotice error={error} />
              <button className="btn btn-primary" type="submit" disabled={!quote.can_checkout}>Review order</button>
            </form>
          ) : (
            <div className="card">
              <h2>Review your order</h2>
              <ul className="review-lines">
                {quote.items.map((i) => (
                  <li key={i.slug}>
                    <span className="review-item"><ProductImage product={i} size="thumb" /><span>{i.quantity} × {i.name}</span></span>
                    <span>{i.line_total}</span>
                  </li>
                ))}
              </ul>
              {quote.problems.map((p) => <p key={p} className="notice notice-warn">{p}</p>)}
              <h3>Ship to</h3>
              <address className="review-address">
                {address.full_name}<br />{address.line1}{address.line2 && <>, {address.line2}</>}<br />
                {address.city}, {address.region} {address.postal_code}, US
              </address>
              <p className="muted">Shipping: {quote.shipping_options.find((o) => o.method === method)?.label}</p>
              <ErrorNotice error={error} />
              <div className="detail-actions">
                <button type="button" className="btn" onClick={() => setStep('shipping')} disabled={busy}>Edit shipping</button>
                <button type="button" className="btn btn-primary" onClick={placeOrder} disabled={busy || !quote.can_checkout}>
                  {busy ? 'Placing order…' : `Place order · ${quote.total}`}
                </button>
              </div>
              <p className="field-help">You’ll pay on the next step. {config.name} payments run in sandbox test mode.</p>
            </div>
          )}
        </div>
        <aside className="card cart-aside" aria-label="Order summary">
          <h2>Summary</h2>
          <CartSummary cart={quote} />
        </aside>
      </div>
    </section>
  );
}

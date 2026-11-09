import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useStore } from '../StoreApp.jsx';
import ProductImage from '../components/ProductImage.jsx';

export function CartSummary({ cart }) {
  return (
    <dl className="totals">
      <div><dt>Subtotal</dt><dd>{cart.subtotal}</dd></div>
      <div><dt>Shipping{cart.shipping_method === 'expedited' ? ' (expedited)' : ''}</dt><dd>{cart.shipping_cents === 0 && cart.items.length ? 'Free' : cart.shipping}</dd></div>
      <div className="totals-total"><dt>Total</dt><dd>{cart.total}</dd></div>
    </dl>
  );
}

export default function CartPage() {
  const { api, session } = useStore();
  const navigate = useNavigate();
  const [cart, setCart] = useState(null);
  const [error, setError] = useState(null);
  const [pending, setPending] = useState(null);

  useEffect(() => {
    api.cart().then(setCart, (e) => setError(e.message));
  }, [api, session]);

  async function change(slug, quantity) {
    setPending(slug);
    setError(null);
    try {
      setCart(quantity === 0 ? await api.removeCartItem(slug) : await api.updateCartItem(slug, quantity));
    } catch (e) {
      setError(e.message);
      api.cart().then(setCart, () => {});
    } finally {
      setPending(null);
    }
  }

  if (session?.customer.role === 'agent') return <p className="empty">Staff accounts can’t shop. Sign in with a customer account.</p>;
  if (!cart) return error ? <p className="notice notice-error" role="alert">{error}</p> : <p className="muted" aria-live="polite">Loading cart…</p>;

  return (
    <section className="page-section">
      <div className="page-head">
        <h1>Your cart{cart.item_count > 0 && <span className="muted page-head-count"> · {cart.item_count} item{cart.item_count === 1 ? '' : 's'}</span>}</h1>
        <Link to="/" className="back-link">← Continue shopping</Link>
      </div>
      {error && <p className="notice notice-error" role="alert">{error}</p>}
      {cart.items.length === 0 ? (
        <div className="empty"><p>Your cart is empty.</p><Link className="btn" to="/">Continue shopping</Link></div>
      ) : (
        <div className="cart-layout">
          <ul className="cart-lines">
            {cart.items.map((i) => (
              <li key={i.slug} className="cart-line">
                <Link to={`/products/${i.slug}`} tabIndex={-1} aria-hidden="true" className="cart-art"><ProductImage product={i} size="thumb" /></Link>
                <div className="cart-line-body">
                  <Link to={`/products/${i.slug}`} className="product-name">{i.name}</Link>
                  <span className="muted">{i.unit_price} each</span>
                  {i.problem && <span className="notice notice-warn cart-problem" role="status">{i.problem}</span>}
                </div>
                <div className="cart-line-actions">
                  <label className="sr-only" htmlFor={`qty-${i.slug}`}>Quantity for {i.name}</label>
                  <select id={`qty-${i.slug}`} value={i.quantity} disabled={pending === i.slug}
                    onChange={(e) => change(i.slug, Number(e.target.value))}>
                    {Array.from({ length: Math.max(i.max_quantity, i.quantity) }, (_, n) => n + 1).map((n) => (
                      <option key={n} value={n} disabled={n > i.max_quantity}>{n}</option>
                    ))}
                  </select>
                  <strong className="cart-line-total">{i.line_total}</strong>
                  <button type="button" className="btn btn-small" disabled={pending === i.slug} onClick={() => change(i.slug, 0)}
                    aria-label={`Remove ${i.name}`}>Remove</button>
                </div>
              </li>
            ))}
          </ul>
          <aside className="card cart-aside" aria-label="Order summary">
            <h2>Summary</h2>
            <CartSummary cart={cart} />
            <p className="field-help">Prices and shipping are calculated by the store. You can choose expedited shipping at checkout where offered.</p>
            <button type="button" className="btn btn-primary btn-block" disabled={!cart.can_checkout}
              onClick={() => navigate(session ? '/checkout' : '/account?next=/checkout')}>
              {session ? 'Checkout' : 'Sign in to check out'}
            </button>
            {!cart.can_checkout && cart.problems.length > 0 && <p className="field-help field-error">Fix the items marked above to continue.</p>}
            {!session && <p className="field-help">Your cart is kept when you sign in or <Link to="/register?next=/checkout">create an account</Link>.</p>}
          </aside>
        </div>
      )}
    </section>
  );
}

import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useStore } from '../StoreApp.jsx';
import { StockBadge } from '../components/ProductCard.jsx';
import ProductImage from '../components/ProductImage.jsx';

const LINE_LIMIT = 10; // the server's per-item limit (it re-checks every request)

export default function ProductPage() {
  const { slug } = useParams();
  const { api, config, info, openChat, session } = useStore();
  const navigate = useNavigate();
  const [state, setState] = useState({ loading: true, product: null, error: null });
  const [inCart, setInCart] = useState(0);
  const [qty, setQty] = useState(1);
  const [qtyText, setQtyText] = useState('1');
  const [cartMsg, setCartMsg] = useState(null);
  const [busy, setBusy] = useState(null); // 'add' | 'buy' while a request is running
  const inFlight = useRef(false);

  useEffect(() => {
    let live = true;
    setState({ loading: true, product: null, error: null });
    setQty(1); setQtyText('1');
    setCartMsg(null);
    api.product(slug).then(
      (d) => live && setState({ loading: false, product: d.product, error: null }),
      (e) => live && setState({ loading: false, product: null, error: e.status === 404 ? 'That product does not exist in this store.' : e.message }),
    );
    return () => { live = false; };
  }, [api, slug]);

  // How many the shopper already has, so the quantity picker never offers more than the server allows.
  useEffect(() => {
    let live = true;
    if (session?.customer.role === 'agent') return undefined;
    api.cart().then((c) => live && setInCart(c.items.find((i) => i.slug === slug)?.quantity || 0), () => {});
    return () => { live = false; };
  }, [api, slug, session]);

  if (state.loading) return <p className="muted page-section" aria-live="polite">Loading…</p>;
  if (state.error) return <div className="empty"><p role="alert">{state.error}</p><Link to="/">Back to the shop</Link></div>;

  const p = state.product;
  const isAgent = session?.customer.role === 'agent';
  const maxAdd = Math.max(0, Math.min(LINE_LIMIT, p.stock_qty) - inCart);
  const qtyValid = Number.isInteger(qty) && qty >= 1 && qty <= maxAdd;

  function setQuantity(n) {
    setQty(n);
    setQtyText(String(n));
  }

  async function add(thenCheckout) {
    if (inFlight.current || !qtyValid) return;
    inFlight.current = true;
    setBusy(thenCheckout ? 'buy' : 'add');
    setCartMsg(null);
    try {
      const cart = await api.addToCart(p.slug, qty);
      setInCart(cart.items.find((i) => i.slug === p.slug)?.quantity || 0);
      if (thenCheckout) {
        // "Buy now" uses the same cart and the same checkout as everything else.
        navigate(session ? '/checkout' : '/account?next=/checkout');
        return;
      }
      setCartMsg({ ok: true, text: `Added ${qty} × ${p.name} to your cart.` });
      setQuantity(1);
    } catch (e) {
      setCartMsg({ ok: false, text: e.message });
      api.cart().then((c) => setInCart(c.items.find((i) => i.slug === p.slug)?.quantity || 0), () => {});
    } finally {
      inFlight.current = false;
      setBusy(null);
    }
  }

  const stockLine = !p.in_stock ? 'Currently out of stock.' : p.stock_qty <= 5 ? `Only ${p.stock_qty} left in stock.` : `${p.stock_qty} in stock.`;

  return (
    <article className="product-detail">
      <nav aria-label="Breadcrumb" className="breadcrumb">
        <Link to="/">Shop</Link> <span aria-hidden="true">/</span> <span>{p.category}</span>
      </nav>
      <div className="detail-grid">
        <ProductImage product={p} size="detail" label />
        <div className="detail-info">
          <p className="product-category">{p.category}</p>
          <h1>{p.name}</h1>
          <p className="detail-price">{p.price}</p>
          <p className="detail-stock"><StockBadge product={p} /> <span>{stockLine}</span></p>
          <p className="detail-desc">{p.description}</p>

          {isAgent ? (
            <p className="notice notice-warn">Staff accounts can’t shop. Sign in with a customer account to buy.</p>
          ) : !p.in_stock ? (
            <div className="buy-box">
              <button type="button" className="btn btn-block" disabled>Out of stock</button>
              <p className="field-help">This item can’t be added to the cart until it’s back in stock.</p>
            </div>
          ) : maxAdd === 0 ? (
            <div className="buy-box">
              <p className="notice notice-warn" role="status">
                You already have {inCart} in your cart, the most you can buy{p.stock_qty < LINE_LIMIT ? ' while stock lasts' : ` (limit ${LINE_LIMIT})`}.
              </p>
              <div className="detail-actions">
                <Link className="btn" to="/cart">View cart</Link>
                <button type="button" className="btn btn-primary" onClick={() => navigate(session ? '/checkout' : '/account?next=/checkout')}>
                  Go to checkout
                </button>
              </div>
            </div>
          ) : (
            <div className="buy-box">
              <label htmlFor="qty" className="qty-label">Quantity</label>
              <div className="qty-stepper">
                <button type="button" className="btn qty-btn" onClick={() => setQuantity(Math.max(1, qty - 1))}
                  disabled={!!busy || qty <= 1} aria-label="Decrease quantity">−</button>
                <input id="qty" type="number" inputMode="numeric" min={1} max={maxAdd} value={qtyText}
                  aria-describedby="qty-help" aria-invalid={!qtyValid}
                  onChange={(e) => { setQtyText(e.target.value); setQty(Number(e.target.value)); }} />
                <button type="button" className="btn qty-btn" onClick={() => setQuantity(Math.min(maxAdd, (qtyValid ? qty : 0) + 1))}
                  disabled={!!busy || qty >= maxAdd} aria-label="Increase quantity">+</button>
              </div>
              <p id="qty-help" className={`field-help ${qtyValid ? '' : 'field-error'}`}>
                {qtyValid
                  ? `You can add up to ${maxAdd}${inCart ? ` (you already have ${inCart} in your cart)` : ''}.`
                  : `Choose a quantity from 1 to ${maxAdd}.`}
              </p>
              <div className="detail-actions">
                <button type="button" className="btn btn-primary" onClick={() => add(false)} disabled={!!busy || !qtyValid}>
                  {busy === 'add' ? 'Adding…' : 'Add to cart'}
                </button>
                <button type="button" className="btn btn-buy" onClick={() => add(true)} disabled={!!busy || !qtyValid}
                  aria-describedby="buy-help">
                  {busy === 'buy' ? 'Adding…' : 'Buy now'}
                </button>
              </div>
              <p id="buy-help" className="field-help">Buy now adds this item to your cart and takes you straight to checkout.</p>
            </div>
          )}

          {cartMsg && (
            <p className={`notice ${cartMsg.ok ? 'notice-ok' : 'notice-error'}`} role={cartMsg.ok ? 'status' : 'alert'}>
              {cartMsg.text} {cartMsg.ok && <><Link to="/cart">View cart</Link> · <Link to={session ? '/checkout' : '/account?next=/checkout'}>Checkout</Link></>}
            </p>
          )}

          <button type="button" className="btn btn-quiet" onClick={() => openChat(`Tell me about the ${p.name}`)}>
            Ask {config.assistantName} about this
          </button>

          {info && (
            <dl className="detail-policies">
              {['shipping', 'returns', 'warranty'].filter((k) => info.policies[k]).map((k) => (
                <div key={k}><dt>{k[0].toUpperCase() + k.slice(1)}</dt><dd>{info.policies[k].summary}</dd></div>
              ))}
            </dl>
          )}
        </div>
      </div>
    </article>
  );
}

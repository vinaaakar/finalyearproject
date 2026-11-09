import React, { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useStore } from '../StoreApp.jsx';
import ProductImage from './ProductImage.jsx';

export function StockBadge({ product }) {
  if (!product.in_stock) return <span className="badge badge-out">Out of stock</span>;
  if (product.stock_qty <= 5) return <span className="badge badge-low">Only {product.stock_qty} left</span>;
  return <span className="badge badge-in">In stock</span>;
}

// Adds one unit through the normal cart API (the server validates stock and limits) and reports the result.
function QuickAdd({ product }) {
  const { api, notify } = useStore();
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  if (!product.in_stock) return <button type="button" className="btn btn-block card-add" disabled>Out of stock</button>;

  async function add() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    try {
      await api.addToCart(product.slug, 1);
      notify({ text: `Added ${product.name} to your cart.`, link: { to: '/cart', label: 'View cart' } });
    } catch (e) {
      notify({ text: e.message, error: true });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <button type="button" className="btn btn-primary btn-block card-add" onClick={add} disabled={busy}
      aria-label={`Add ${product.name} to cart`}>
      {busy ? 'Adding…' : 'Add to cart'}
    </button>
  );
}

export default function ProductCard({ product, compact = false }) {
  const { session } = useStore();
  if (compact) {
    // Inside the chat: a small link card.
    return (
      <Link to={`/products/${product.slug}`} className="product-card product-card-compact">
        <ProductImage product={product} size="thumb" />
        <span className="product-body">
          <span className="product-name">{product.name}</span>
          <span className="product-meta"><span className="price">{product.price}</span><StockBadge product={product} /></span>
        </span>
      </Link>
    );
  }
  return (
    <article className="product-card">
      <ProductImage product={product} />
      <div className="product-body">
        <p className="product-category">{product.category}</p>
        {/* The title link stretches over the whole card; the add button sits above it. */}
        <h3 className="product-name"><Link to={`/products/${product.slug}`} className="card-link">{product.name}</Link></h3>
        <p className="product-desc">{product.description}</p>
        <div className="product-meta">
          <span className="price">{product.price}</span>
          <StockBadge product={product} />
        </div>
        {session?.customer.role !== 'agent' && <QuickAdd product={product} />}
      </div>
    </article>
  );
}

import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useStore } from '../StoreApp.jsx';
import { StockBadge } from '../components/ProductCard.jsx';

export default function ProductPage() {
  const { slug } = useParams();
  const { api, config, openChat } = useStore();
  const [state, setState] = useState({ loading: true, product: null, error: null });

  useEffect(() => {
    let live = true;
    setState({ loading: true, product: null, error: null });
    api.product(slug).then(
      (d) => live && setState({ loading: false, product: d.product, error: null }),
      (e) => live && setState({ loading: false, product: null, error: e.status === 404 ? 'That product does not exist in this store.' : e.message }),
    );
    return () => { live = false; };
  }, [api, slug]);

  if (state.loading) return <p className="muted" aria-live="polite">Loading…</p>;
  if (state.error) return <div className="empty"><p role="alert">{state.error}</p><Link to="/">Back to the shop</Link></div>;

  const p = state.product;
  return (
    <article className="product-detail">
      <Link to="/" className="back-link">← All products</Link>
      <div className="detail-grid">
        <div className="detail-art" aria-hidden="true">{p.emoji}</div>
        <div>
          <p className="product-category">{p.category}</p>
          <h1>{p.name}</h1>
          <p className="detail-price">{p.price} <StockBadge product={p} /></p>
          <p className="detail-desc">{p.description}</p>
          <div className="detail-actions">
            <button type="button" className="btn btn-primary" disabled title="Checkout is outside this demo's scope">
              Add to cart (demo)
            </button>
            <button type="button" className="btn" onClick={() => openChat(`Tell me about the ${p.name}`)}>
              Ask {config.assistantName} about this
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}

import React, { useEffect, useState } from 'react';
import { useStore } from '../StoreApp.jsx';
import ProductCard from '../components/ProductCard.jsx';

export default function HomePage() {
  const { api, config, openChat } = useStore();
  const [categories, setCategories] = useState([]);
  const [category, setCategory] = useState('');
  const [query, setQuery] = useState('');
  const [submitted, setSubmitted] = useState('');
  const [state, setState] = useState({ loading: true, products: [], error: null });

  useEffect(() => {
    api.categories().then((d) => setCategories(d.categories), () => {});
  }, [api]);

  useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    api.products({ q: submitted, category }).then(
      (d) => live && setState({ loading: false, products: d.products, error: null }),
      (e) => live && setState({ loading: false, products: [], error: e.message }),
    );
    return () => { live = false; };
  }, [api, submitted, category]);

  return (
    <>
      <section className="hero">
        <div>
          <h1>{config.heroTitle}</h1>
          <p>{config.heroText}</p>
          <button type="button" className="btn btn-primary" onClick={() => openChat()}>
            Ask {config.assistantName} — by chat or voice
          </button>
        </div>
        <span className="hero-art" aria-hidden="true">{config.heroEmoji}</span>
      </section>

      <section aria-labelledby="catalog-heading">
        <div className="catalog-bar">
          <h2 id="catalog-heading">Shop {category || 'all products'}</h2>
          <form className="search" role="search" onSubmit={(e) => { e.preventDefault(); setSubmitted(query.trim()); }}>
            <label htmlFor="product-search" className="sr-only">Search products</label>
            <input id="product-search" type="search" value={query} maxLength={100}
              placeholder="Search products" onChange={(e) => setQuery(e.target.value)} />
            <button className="btn" type="submit">Search</button>
          </form>
        </div>
        <div className="chips" role="group" aria-label="Filter by category">
          {['', ...categories].map((c) => (
            <button key={c || 'all'} type="button" className={`chip ${category === c ? 'chip-active' : ''}`}
              aria-pressed={category === c} onClick={() => setCategory(c)}>
              {c || 'All'}
            </button>
          ))}
        </div>

        {state.error && <p className="notice notice-error" role="alert">{state.error}</p>}
        {state.loading ? (
          <p className="muted" aria-live="polite">Loading products…</p>
        ) : state.products.length === 0 && !state.error ? (
          <p className="empty">No products match. Try another search or ask {config.assistantName}.</p>
        ) : (
          <ul className="product-grid">
            {state.products.map((p) => <li key={p.slug}><ProductCard product={p} /></li>)}
          </ul>
        )}
      </section>
    </>
  );
}

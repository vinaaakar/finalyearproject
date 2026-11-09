import React, { useEffect, useState } from 'react';
import { useStore } from '../StoreApp.jsx';
import ProductCard from '../components/ProductCard.jsx';

// Short store facts for the strip under the hero, taken from the store's own policy data.
export function PolicyStrip({ info }) {
  if (!info) return null;
  const items = [
    ['shipping', 'Shipping'],
    ['returns', 'Returns'],
  ].filter(([k]) => info.policies[k]);
  return (
    <ul className="policy-strip">
      {items.map(([k, title]) => (
        <li key={k}><strong>{title}</strong><span>{info.policies[k].summary}</span></li>
      ))}
      <li><strong>Secure checkout</strong><span>Test-mode payments: no card details are ever collected.</span></li>
    </ul>
  );
}

export default function HomePage() {
  const { api, config, info, openChat } = useStore();
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

  const count = state.products.length;
  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <p className="hero-eyebrow">{config.tagline}</p>
          <h1>{config.heroTitle}</h1>
          <p>{config.heroText}</p>
          <div className="hero-actions">
            <a className="btn btn-primary" href="#catalog-heading">Shop the collection</a>
            <button type="button" className="btn btn-on-hero" onClick={() => openChat()}>
              Ask {config.assistantName} — chat or voice
            </button>
          </div>
        </div>
        <div className="hero-art">{config.heroArt}</div>
      </section>

      <PolicyStrip info={info} />

      <section aria-labelledby="catalog-heading" className="catalog">
        <div className="catalog-bar">
          <div>
            <h2 id="catalog-heading">{category || (submitted ? 'Search results' : 'All products')}</h2>
            {!state.loading && !state.error && (
              <p className="muted catalog-count" aria-live="polite">
                {count} product{count === 1 ? '' : 's'}{submitted ? ` matching “${submitted}”` : ''}
              </p>
            )}
          </div>
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
          {submitted && (
            <button type="button" className="chip" onClick={() => { setQuery(''); setSubmitted(''); }}>Clear search ✕</button>
          )}
        </div>

        {state.error && <p className="notice notice-error" role="alert">{state.error}</p>}
        {state.loading ? (
          <p className="muted" aria-live="polite">Loading products…</p>
        ) : count === 0 && !state.error ? (
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

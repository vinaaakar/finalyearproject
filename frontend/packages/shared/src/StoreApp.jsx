import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { BrowserRouter, Link, NavLink, Route, Routes } from 'react-router-dom';
import { SESSION_EVENT, createApi } from './api.js';
import ChatWidget from './ChatWidget.jsx';
import HomePage from './pages/HomePage.jsx';
import ProductPage from './pages/ProductPage.jsx';
import AccountPage from './pages/AccountPage.jsx';

const StoreContext = createContext(null);
export const useStore = () => useContext(StoreContext);

export default function StoreApp({ config }) {
  const api = useMemo(() => createApi(config.storeId), [config.storeId]);
  const [info, setInfo] = useState(null);
  const [infoError, setInfoError] = useState(null);
  const [session, setSession] = useState(() => api.loadSession());
  const [chat, setChat] = useState({ open: false, prefill: '' });

  useEffect(() => {
    const sync = () => setSession(api.loadSession());
    window.addEventListener(SESSION_EVENT, sync);
    return () => window.removeEventListener(SESSION_EVENT, sync);
  }, [api]);

  useEffect(() => {
    document.title = config.name;
    api.store().then(setInfo, (e) => setInfoError(e.message));
  }, [api, config.name]);

  const openChat = useCallback((prefill = '') => setChat({ open: true, prefill }), []);
  const closeChat = useCallback(() => setChat({ open: false, prefill: '' }), []);

  const value = { api, config, info, session, openChat };

  return (
    <StoreContext.Provider value={value}>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <a className="skip-link" href="#main">Skip to content</a>
        <header className="site-header">
          <div className="container header-inner">
            <Link to="/" className="brand" aria-label={`${config.name} home`}>
              <span className="brand-mark" aria-hidden="true">{config.logo}</span>
              <span>
                <span className="brand-name">{config.name}</span>
                <span className="brand-tagline">{config.tagline}</span>
              </span>
            </Link>
            <nav className="main-nav" aria-label="Main">
              <NavLink to="/" end>Shop</NavLink>
              <NavLink to="/account">{session ? `Hi, ${session.customer.name.split(' ')[0]}` : 'Sign in'}</NavLink>
              <button type="button" className="btn btn-ghost" onClick={() => openChat()}>Help</button>
            </nav>
          </div>
        </header>

        <main id="main" className="container">
          {infoError && <p className="notice notice-error" role="alert">{infoError}</p>}
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/products/:slug" element={<ProductPage />} />
            <Route path="/account" element={<AccountPage />} />
            <Route path="*" element={<div className="empty"><h1>Page not found</h1><Link to="/">Back to the shop</Link></div>} />
          </Routes>
        </main>

        <footer className="site-footer">
          <div className="container footer-grid">
            <div>
              <strong>{config.name}</strong>
              {info && <p>{info.support_email}<br />{info.support_hours}</p>}
            </div>
            {info && ['shipping', 'returns'].map((t) => info.policies[t] && (
              <div key={t}>
                <strong>{t === 'shipping' ? 'Shipping' : 'Returns'}</strong>
                <p>{info.policies[t].summary}</p>
              </div>
            ))}
            <p className="footer-note">Demo store with synthetic data. No real orders are placed.</p>
          </div>
        </footer>

        <ChatWidget open={chat.open} prefill={chat.prefill} onOpen={() => openChat()} onClose={closeChat} />
      </BrowserRouter>
    </StoreContext.Provider>
  );
}

import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { BrowserRouter, Link, NavLink, Route, Routes } from 'react-router-dom';
import { CART_EVENT, SESSION_EVENT, createApi } from './api.js';
import ChatWidget from './ChatWidget.jsx';
import HomePage from './pages/HomePage.jsx';
import ProductPage from './pages/ProductPage.jsx';
import AccountPage from './pages/AccountPage.jsx';
import CartPage from './pages/CartPage.jsx';
import CheckoutPage from './pages/CheckoutPage.jsx';
import PaymentPage from './pages/PaymentPage.jsx';
import { ForgotPasswordPage, RegisterPage, ResetPasswordPage } from './pages/AuthPages.jsx';

const StoreContext = createContext(null);
export const useStore = () => useContext(StoreContext);

export default function StoreApp({ config }) {
  const api = useMemo(() => createApi(config.storeId), [config.storeId]);
  const [info, setInfo] = useState(null);
  const [infoError, setInfoError] = useState(null);
  const [session, setSession] = useState(() => api.loadSession());
  const [chat, setChat] = useState({ open: false, prefill: '' });
  const [cartCount, setCartCount] = useState(0);
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);

  useEffect(() => {
    const sync = () => setSession(api.loadSession());
    window.addEventListener(SESSION_EVENT, sync);
    return () => window.removeEventListener(SESSION_EVENT, sync);
  }, [api]);

  // Header cart count: refreshed from the server on sign-in/out and whenever the cart changes.
  useEffect(() => {
    let live = true;
    const refresh = () => api.cart().then((c) => live && setCartCount(c.item_count), () => live && setCartCount(0));
    const onCart = (e) => (e.detail ? setCartCount(e.detail.item_count) : refresh());
    refresh();
    window.addEventListener(CART_EVENT, onCart);
    return () => { live = false; window.removeEventListener(CART_EVENT, onCart); };
  }, [api, session]);

  useEffect(() => {
    document.title = config.name;
    api.store().then(setInfo, (e) => setInfoError(e.message));
  }, [api, config.name]);

  const openChat = useCallback((prefill = '') => setChat({ open: true, prefill }), []);
  const closeChat = useCallback(() => setChat({ open: false, prefill: '' }), []);

  // Short confirmation/error messages (e.g. "Added … to your cart"), announced politely to screen readers.
  const notify = useCallback((t) => {
    clearTimeout(toastTimer.current);
    setToast({ ...t, id: Date.now() });
    toastTimer.current = setTimeout(() => setToast(null), t.error ? 7000 : 5000);
  }, []);
  useEffect(() => () => clearTimeout(toastTimer.current), []);

  const value = { api, config, info, session, openChat, notify };

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
              {session?.customer.role !== 'agent' && (
                <NavLink to="/cart" className="nav-cart" aria-label={`Cart, ${cartCount} item${cartCount === 1 ? '' : 's'}`}>
                  Cart<span className={`cart-count ${cartCount > 0 ? '' : 'cart-count-empty'}`} aria-hidden="true">{cartCount}</span>
                </NavLink>
              )}
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
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            <Route path="/cart" element={<CartPage />} />
            <Route path="/checkout" element={<CheckoutPage />} />
            <Route path="/orders/:number/pay" element={<PaymentPage />} />
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
            <p className="footer-note">Demo store with synthetic data. Payments run in sandbox test mode: no real money moves and no card details are collected.</p>
          </div>
        </footer>

        <div className="toast-region" role="status" aria-live="polite">
          {toast && (
            <p key={toast.id} className={`toast ${toast.error ? 'toast-error' : ''}`}>
              <span>{toast.text}</span>
              {toast.link && <Link to={toast.link.to} onClick={() => setToast(null)}>{toast.link.label}</Link>}
              <button type="button" className="toast-close" onClick={() => setToast(null)} aria-label="Dismiss">✕</button>
            </p>
          )}
        </div>

        <ChatWidget open={chat.open} prefill={chat.prefill} onOpen={() => openChat()} onClose={closeChat} />
      </BrowserRouter>
    </StoreContext.Provider>
  );
}

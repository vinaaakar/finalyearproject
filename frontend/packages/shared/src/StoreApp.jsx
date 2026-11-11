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
import OrderDetailPage from './pages/OrderDetailPage.jsx';
import { StaffOrderPage, StaffOrdersPage } from './pages/StaffPages.jsx';
import { StaffCarePage, StaffCareRequestPage } from './pages/StaffCarePages.jsx';
import { CareNewPage, CareRequestPage, CareRequestsPage } from './pages/CarePages.jsx';
import { ContactPage, HelpPage, ReturnsPage, ShippingPage } from './pages/SupportPages.jsx';
import CallPage from './pages/CallPage.jsx';
import { ForgotPasswordPage, RegisterPage, ResetPasswordPage } from './pages/AuthPages.jsx';
import { UI_LANGUAGES, ui } from './uiText.js';
import { DELIVERY_COUNTRY } from './currency.js';

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
  // Interface language (Phase I): remembered per store in this browser; English unless the shopper chooses otherwise.
  const langKey = `avc:${config.storeId}:ui-language`;
  const [uiLang, setUiLangState] = useState(() => {
    try {
      const v = localStorage.getItem(langKey);
      return UI_LANGUAGES.some(([c]) => c === v) ? v : 'en';
    } catch {
      return 'en';
    }
  });
  const setUiLang = useCallback((v) => {
    setUiLangState(v);
    try { localStorage.setItem(langKey, v); } catch { /* not remembered */ }
  }, [langKey]);
  const t = useCallback((key, vars) => ui(uiLang, key, vars), [uiLang]);
  // India-only stores: prices in ₹, delivery to Indian addresses.
  const deliveryCountry = DELIVERY_COUNTRY;
  useEffect(() => {
    document.documentElement.lang = UI_LANGUAGES.find(([c]) => c === uiLang)?.[2] || 'en';
  }, [uiLang]);

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
    api.store(uiLang).then(setInfo, (e) => setInfoError(e.message));   // policies in the interface language
  }, [api, config.name, uiLang]);

  const openChat = useCallback((prefill = '') => setChat({ open: true, prefill }), []);
  const closeChat = useCallback(() => setChat({ open: false, prefill: '' }), []);

  // Short confirmation/error messages (e.g. "Added … to your cart"), announced politely to screen readers.
  const notify = useCallback((t) => {
    clearTimeout(toastTimer.current);
    setToast({ ...t, id: Date.now() });
    toastTimer.current = setTimeout(() => setToast(null), t.error ? 7000 : 5000);
  }, []);
  useEffect(() => () => clearTimeout(toastTimer.current), []);

  const value = { api, config, info, infoError, session, openChat, notify, uiLang, setUiLang, t, deliveryCountry };

  return (
    <StoreContext.Provider value={value}>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <a className="skip-link" href="#main">{t('skip')}</a>
        <header className="site-header">
          <div className="container header-inner">
            <Link to="/" className="brand" aria-label={`${config.name} home`}>
              <span className="brand-mark" aria-hidden="true">{config.logo}</span>
              <span>
                <span className="brand-name">{config.name}</span>
                <span className="brand-tagline">{config.tagline}</span>
              </span>
            </Link>
            <nav className="main-nav" aria-label={t('mainNav')}>
              <NavLink to="/" end>{t('shop')}</NavLink>
              <NavLink to="/account">{session ? t('hi', { name: session.customer.name.split(' ')[0] }) : t('signIn')}</NavLink>
              {session?.customer.role === 'agent' && <NavLink to="/staff/orders">{t('fulfilment')}</NavLink>}
              {session?.customer.role === 'agent' && <NavLink to="/staff/care">{t('customerCare')}</NavLink>}
              {session?.customer.role !== 'agent' && (
                <NavLink to="/cart" className="nav-cart" aria-label={t('cartLabel', { n: cartCount, s: cartCount === 1 ? '' : 's' })}>
                  {t('cart')}<span className={`cart-count ${cartCount > 0 ? '' : 'cart-count-empty'}`} aria-hidden="true">{cartCount}</span>
                </NavLink>
              )}
              <button type="button" className="btn btn-ghost" onClick={() => openChat()}>{t('help')}</button>
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
            <Route path="/orders/:number" element={<OrderDetailPage />} />
            <Route path="/staff/orders" element={<StaffOrdersPage />} />
            <Route path="/staff/orders/:number" element={<StaffOrderPage />} />
            <Route path="/staff/care" element={<StaffCarePage />} />
            <Route path="/staff/care/:ref" element={<StaffCareRequestPage />} />
            <Route path="/support/requests" element={<CareRequestsPage />} />
            <Route path="/support/requests/:ref" element={<CareRequestPage />} />
            <Route path="/support/new" element={<CareNewPage />} />
            <Route path="/support/call" element={<CallPage />} />
            <Route path="/help" element={<HelpPage />} />
            <Route path="/shipping" element={<ShippingPage />} />
            <Route path="/returns" element={<ReturnsPage />} />
            <Route path="/contact" element={<ContactPage />} />
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
            <nav className="footer-nav" aria-label={t('customerService')}>
              <Link to="/help">{t('help')}</Link>
              <Link to="/shipping">{t('shipping')}</Link>
              <Link to="/returns">{t('returns')}</Link>
              <Link to="/contact">{t('contact')}</Link>
            </nav>
            <label className="footer-lang">
              {t('language')}{' '}
              <select value={uiLang} onChange={(e) => setUiLang(e.target.value)} data-testid="ui-language">
                {UI_LANGUAGES.map(([code, name, bcp]) => <option key={code} value={code} lang={bcp}>{name}</option>)}
              </select>
            </label>
            <p className="footer-note">{t('demoNote')}</p>
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

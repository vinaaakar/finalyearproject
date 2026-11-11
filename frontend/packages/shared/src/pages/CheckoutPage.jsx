import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { newIdempotencyKey } from '../api.js';
import { useStore } from '../StoreApp.jsx';
import { CartSummary, PriceNotice } from './CartPage.jsx';
import { ErrorNotice } from './AuthPages.jsx';
import ProductImage from '../components/ProductImage.jsx';
import AddressCard from '../components/AddressCard.jsx';

// Country-aware checkout. The server describes every country the store's checkout offers (GET /checkout/address-options:
// regions with their names, postal format, phone, labels, currency, whether delivery rates and prices exist) and prices
// the order for the chosen destination in that destination's currency. There is NO built-in fallback form: if the
// countries can't be loaded the page says so and offers a retry, rather than silently showing a US-only form (which is
// what an Indian customer saw while the server was older: US state codes such as "TN" = Tennessee, ZIP validation,
// "United States addresses only" and US shipping).
const EMPTY = { full_name: '', line1: '', line2: '', city: '', region: '', postal_code: '', phone: '', country: '' };
// HTML pattern attributes are anchored already.
const htmlPattern = (p) => p.replace(/^\^/, '').replace(/\$$/, '');
const CURRENCY_NAMES = { INR: 'Indian rupees (₹)', USD: 'US dollars ($)' };

export default function CheckoutPage() {
  const { api, session, config, deliveryCountry } = useStore();
  const navigate = useNavigate();
  const [step, setStep] = useState('shipping');
  const [address, setAddress] = useState(() => ({ ...EMPTY, full_name: session?.customer.name || '' }));
  const [method, setMethod] = useState('standard');
  const [quote, setQuote] = useState(null);
  const [error, setError] = useState(null);
  const [optionsError, setOptionsError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [countries, setCountries] = useState(null);   // the countries this store ships to, with their rules
  const [savedAddresses, setSavedAddresses] = useState([]);
  const [addressMode, setAddressMode] = useState('form'); // 'card' or 'form'
  const [saveAddress, setSaveAddress] = useState(false);   // opt-in: the customer must tick "Save this address"
  const [makeDefault, setMakeDefault] = useState(false);
  const [addressLabel, setAddressLabel] = useState('Home');
  // One key per review: resubmitting (double click, retry after a network error) cannot create a second order.
  const idemKey = useRef(newIdempotencyKey());
  const set = (k) => (e) => setAddress((a) => ({ ...a, [k]: e.target.value }));
  const country = countries?.find((c) => c.code === address.country) || null;

  const loadAddresses = useCallback(() => {
    if (!session || !api.addresses) return;
    api.addresses().then(
      (d) => {
        const list = d?.addresses || [];
        setSavedAddresses(list);
        if (list.length > 0) {
          const def = list.find((a) => a.is_default) || list[0];
          setAddress({
            full_name: def.full_name,
            line1: def.line1,
            line2: def.line2 || '',
            city: def.city,
            region: def.region,
            postal_code: def.postal_code,
            phone: def.phone || '',
            country: def.country || 'IN',
          });
          setAddressLabel(def.label || 'Home');
          setAddressMode('card');
        } else {
          setAddressMode('form');
        }
      },
      () => setAddressMode('form')
    );
  }, [api, session]);
  useEffect(() => { loadAddresses(); }, [loadAddresses]);

  const loadOptions = useCallback(() => {
    if (!session) return () => {};
    let live = true;
    setOptionsError(null);
    api.addressOptions().then((d) => {
      if (!live) return;
      if (!d?.countries?.length) { setOptionsError(new Error('This store has no delivery countries set up.')); return; }
      setCountries(d.countries);
      // The shopper's own choice ("Deliver to") wins; otherwise the server's default (last order's country, else the store's).
      const chosen = d.countries.some((c) => c.code === deliveryCountry) ? deliveryCountry : null;
      setAddress((a) => ({ ...a, country: chosen || d.default_country || d.countries[0].code }));
    }, (e) => live && setOptionsError(e));
    return () => { live = false; };
  }, [api, session]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => loadOptions(), [loadOptions]);

  // Prices for the destination: the country (and, once complete, state and postal code) decide currency and rates.
  const postalOk = !!country && new RegExp(country.postal_pattern).test(address.postal_code);
  const destination = country ? { country: country.code, ...(address.region ? { region: address.region } : {}),
    ...(postalOk ? { postal_code: address.postal_code } : {}) } : null;
  const destKey = destination ? JSON.stringify(destination) : '';
  useEffect(() => {
    if (!session || !destination) return;
    let live = true;
    api.quote(method, destination).then((q) => live && setQuote(q), (e) => live && setError(e));
    return () => { live = false; };
  }, [api, session, method, destKey]);   // eslint-disable-line react-hooks/exhaustive-deps

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
  if (optionsError) {
    return (
      <div className="card form">
        <h1>Checkout</h1>
        <p className="notice notice-error" role="alert">
          The delivery countries couldn’t be loaded, so checkout can’t continue yet. Nothing has been ordered and your cart is kept.
        </p>
        <button type="button" className="btn btn-primary" onClick={loadOptions}>Try again</button>
      </div>
    );
  }
  if (!quote || !country) return error ? <ErrorNotice error={error} /> : <p className="muted" aria-live="polite">Loading…</p>;
  if (quote.items.length === 0) return <div className="empty"><p>Your cart is empty.</p><Link className="btn" to="/">Continue shopping</Link></div>;

  // Amounts are shown only in the destination's own currency (never another currency's figures relabelled).
  // A quote in another currency than the destination's (e.g. an older server pricing India in US dollars) is shown with
  // no amounts and no shipping options at all.
  const foreign = !!country.currency && quote.currency !== country.currency;
  const view = foreign ? { ...quote, currency: country.currency, prices_available: false, shipping: null, shipping_cents: null,
    shipping_options: [], shipping_available: false, items: quote.items.map((i) => ({ ...i, line_total: null, unit_price: null })) } : quote;
  const priced = view.prices_available !== false;
  const shippingAvailable = view.shipping_available !== false && view.shipping_options.length > 0;
  const stockProblems = quote.problems.length > 0;
  const canPlace = priced && shippingAvailable && quote.can_checkout;

  function changeCountry(e) {
    const code = e.target.value;
    // State and postal code belong to one country; everything else the customer typed is kept.
    setAddress((a) => ({ ...a, country: code, region: '', postal_code: '' }));
    setMethod('standard');
  }

  function selectAddress(addr) {
    setAddress({
      full_name: addr.full_name,
      line1: addr.line1,
      line2: addr.line2 || '',
      city: addr.city,
      region: addr.region,
      postal_code: addr.postal_code,
      phone: addr.phone || '',
      country: addr.country || 'IN',
    });
    setAddressLabel(addr.label || 'Home');
  }

  function deliverTo(addr) {
    selectAddress(addr);
    setError(null);
    idemKey.current = newIdempotencyKey();
    setStep('review');
  }

  function editCard(addr) {
    selectAddress(addr);
    setAddressLabel(addr.label || 'Home');
    setMakeDefault(Boolean(addr.is_default));
    setAddressMode('form');
  }

  function addNewAddress() {
    setAddress({ ...EMPTY, full_name: session?.customer.name || '', country: countries?.[0]?.code || 'IN' });
    setSaveAddress(false);
    setMakeDefault(false);
    setAddressLabel('Home');
    setAddressMode('form');
  }

  async function handleSetDefault(id) {
    if (!api.setDefaultAddress) return;
    await api.setDefaultAddress(id);
    loadAddresses();
  }

  async function handleDelete(id) {
    if (!api.deleteAddress) return;
    if (window.confirm('Delete this saved address?')) {
      await api.deleteAddress(id);
      loadAddresses();
    }
  }

  function toReview(e) {
    e.preventDefault();
    setError(null);
    idemKey.current = newIdempotencyKey();
    setStep('review');
  }

  function shippingBody() {
    const { phone, ...base } = address;
    return { ...base, line2: address.line2.trim() || null, ...(phone.trim() ? { phone: phone.trim() } : {}) };
  }

  async function placeOrder() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.checkout({
        shipping: shippingBody(),
        shippingMethod: method,
        expectedTotalCents: quote.total_cents,
        idempotencyKey: idemKey.current,
        // Opt-in only: the box is unchecked by default, and is shown only on the address form (a saved card is
        // already saved), so nothing is sent unless the customer ticked it on the form they used.
        saveAddress: addressMode === 'form' && saveAddress === true,
        makeDefault: addressMode === 'form' && saveAddress === true && makeDefault,
        addressLabel: addressLabel || 'Home',
      });
      navigate(`/orders/${r.order.order_number}/pay`, { replace: true });
    } catch (e) {
      setError(e);
      if (e.status === 409 || e.status === 422) {
        // Prices, stock or the address changed/failed: show the server's current numbers and let the customer re-review.
        api.quote(method, destination).then(setQuote, () => {});
        idemKey.current = newIdempotencyKey();
      }
      if (e.status === 422) setStep('shipping');
    } finally {
      setBusy(false);
    }
  }

  const regionName = country.regions.find((r) => r.code === address.region)?.name || address.region;
  const shippingNotice = (
    <p className="notice notice-warn" role="status">
      Shipping rates not configured: {config.name} hasn’t set delivery rates for {country.name}
      {address.region ? ` (${regionName})` : ''} yet, so an order can’t be placed. Your cart is kept.
    </p>
  );

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
            addressMode === 'card' && savedAddresses.length > 0 ? (
              <div className="card checkout-saved-addresses" data-testid="checkout-saved-addresses">
                <div className="section-head" style={{ marginTop: 0 }}>
                  <h2>Select delivery address</h2>
                  <button type="button" className="btn btn-small" onClick={addNewAddress}>
                    + Add a new address
                  </button>
                </div>
                <p className="muted">Choose a delivery address from your saved addresses below.</p>

                <div className="address-grid">
                  {savedAddresses.map((addr) => {
                    const isSelected =
                      address.line1 === addr.line1 &&
                      address.postal_code === addr.postal_code &&
                      address.city === addr.city;
                    return (
                      <AddressCard
                        key={addr.id}
                        address={addr}
                        mode="checkout"
                        isSelected={isSelected}
                        onSelect={deliverTo}
                        onEdit={editCard}
                        onSetDefault={handleSetDefault}
                        onDelete={handleDelete}
                      />
                    );
                  })}
                </div>

                <PriceNotice cart={view} storeName={config.name} />
                {!shippingAvailable ? shippingNotice : (
                  <fieldset className="ship-methods">
                    <legend>Shipping method</legend>
                    {view.shipping_options.map((o) => (
                      <label key={o.method} className="radio">
                        <input type="radio" name="ship-method" value={o.method} checked={method === o.method} onChange={() => setMethod(o.method)} />
                        {o.label}{priced && <> — {o.cents === 0 ? 'Free' : o.price}</>}
                      </label>
                    ))}
                  </fieldset>
                )}
                <ErrorNotice error={error} />
                <div className="detail-actions" style={{ marginTop: '16px' }}>
                  <button type="button" className="btn btn-primary" onClick={toReview} disabled={stockProblems}>
                    Deliver to this address
                  </button>
                  <button type="button" className="btn" onClick={addNewAddress}>
                    Add a new address
                  </button>
                </div>
              </div>
            ) : (
              <form className="card checkout-form" onSubmit={toReview}>
                <div className="section-head" style={{ marginTop: 0 }}>
                  <h2>Shipping address</h2>
                  {savedAddresses.length > 0 && (
                    <button type="button" className="btn btn-small" onClick={() => setAddressMode('card')}>
                      ← Use a saved address
                    </button>
                  )}
                </div>
                {countries.length > 1 ? (
                  <>
                    <label htmlFor="ship-country">Country / Region</label>
                    <select id="ship-country" autoComplete="shipping country" required value={address.country} onChange={changeCountry}>
                      {countries.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
                    </select>
                  </>
                ) : (
                  <p className="checkout-country" data-testid="ship-country">Delivering to <strong>{country.name}</strong></p>
                )}
                <label htmlFor="ship-name">Full name</label>
                <input id="ship-name" autoComplete="shipping name" required maxLength={100} value={address.full_name} onChange={set('full_name')} />
                <label htmlFor="ship-line1">{country.line1_label}</label>
                <input id="ship-line1" autoComplete="shipping address-line1" required maxLength={120} value={address.line1} onChange={set('line1')} />
                <label htmlFor="ship-line2">{country.line2_label}</label>
                <input id="ship-line2" autoComplete="shipping address-line2" maxLength={120} value={address.line2} onChange={set('line2')} />
                <div className="form-row">
                  <div>
                    <label htmlFor="ship-city">{country.city_label}</label>
                    <input id="ship-city" autoComplete="shipping address-level2" required maxLength={80} value={address.city} onChange={set('city')} />
                  </div>
                  <div>
                    <label htmlFor="ship-region">{country.region_label}</label>
                    <select id="ship-region" autoComplete="shipping address-level1" required value={address.region} onChange={set('region')}>
                      <option value="">Select…</option>
                      {country.regions.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="ship-zip">{country.postal_label}</label>
                    {/* key: a new input per country, so no previous country's pattern or value survives a switch */}
                    <input key={country.code} id="ship-zip" autoComplete="shipping postal-code" inputMode="numeric" required
                      pattern={htmlPattern(country.postal_pattern)} title={`${country.postal_label}, for example ${country.postal_example}`}
                      maxLength={country.code === 'IN' ? 6 : 10} value={address.postal_code} onChange={set('postal_code')} />
                  </div>
                </div>
                {country.phone && (
                  <>
                    <label htmlFor="ship-phone">{country.phone.required ? 'Mobile number' : 'Phone number (optional)'}</label>
                    <div className="phone-field">
                      <span className="phone-prefix" aria-hidden="true">{country.phone.dial_code}</span>
                      <input id="ship-phone" type="tel" autoComplete="shipping tel-national" inputMode="tel" required={country.phone.required}
                        maxLength={20} pattern="[+0-9 ().\-]{10,20}" aria-describedby="ship-phone-help"
                        title={`10-digit number, for example ${country.phone.example}`} value={address.phone} onChange={set('phone')} />
                    </div>
                    <p id="ship-phone-help" className="field-help">Country code {country.phone.dial_code}. For example {country.phone.example}.</p>
                  </>
                )}
                <div className="checkout-save-options">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={saveAddress}
                      onChange={(e) => setSaveAddress(e.target.checked)}
                    />
                    <span>Save this address to your account</span>
                  </label>
                  {saveAddress && (
                    <label className="checkbox-label" style={{ marginLeft: '12px' }}>
                      <input
                        type="checkbox"
                        checked={makeDefault}
                        onChange={(e) => setMakeDefault(e.target.checked)}
                      />
                      <span>Make this my default address</span>
                    </label>
                  )}
                </div>
                <PriceNotice cart={view} storeName={config.name} />
                {!shippingAvailable ? shippingNotice : (
                  <fieldset className="ship-methods">
                    <legend>Shipping method</legend>
                    {view.shipping_options.map((o) => (
                      <label key={o.method} className="radio">
                        <input type="radio" name="ship-method" value={o.method} checked={method === o.method} onChange={() => setMethod(o.method)} />
                        {o.label}{priced && <> — {o.cents === 0 ? 'Free' : o.price}</>}
                      </label>
                    ))}
                  </fieldset>
                )}
                <ErrorNotice error={error} />
                <button className="btn btn-primary" type="submit" disabled={stockProblems}>Review order</button>
              </form>
            )
          ) : (
            <div className="card">
              <h2>Review your order</h2>
              <ul className="review-lines">
                {view.items.map((i) => (
                  <li key={i.slug}>
                    <span className="review-item"><ProductImage product={i} size="thumb" /><span>{i.quantity} × {i.name}</span></span>
                    <span>{priced && i.line_total ? i.line_total : 'Price not set'}</span>
                  </li>
                ))}
              </ul>
              {quote.problems.map((p) => <p key={p} className="notice notice-warn">{p}</p>)}
              <h3>Ship to</h3>
              <address className="review-address">
                {address.full_name}<br />{address.line1}{address.line2 && <>, {address.line2}</>}<br />
                {address.city}, {regionName} {address.postal_code}, {country.name}
                {address.phone.trim() && <><br />{address.phone.trim().startsWith('+') ? address.phone.trim() : `${country.phone?.dial_code || ''} ${address.phone.trim()}`}</>}
              </address>
              {priced && <p className="muted">Prices in {CURRENCY_NAMES[quote.currency] || quote.currency}.</p>}
              <PriceNotice cart={view} storeName={config.name} />
              {shippingAvailable
                ? <p className="muted">Shipping: {view.shipping_options.find((o) => o.method === method)?.label}</p>
                : shippingNotice}
              <ErrorNotice error={error} />
              <div className="detail-actions">
                <button type="button" className="btn" onClick={() => setStep('shipping')} disabled={busy}>Edit shipping</button>
                <button type="button" className="btn btn-primary" onClick={placeOrder} disabled={busy || !canPlace}>
                  {busy ? 'Placing order…' : canPlace ? `Place order · ${quote.total}` : 'Place order'}
                </button>
              </div>
              <p className="field-help">You’ll pay on the next step. {config.name} payments run in sandbox test mode.</p>
            </div>
          )}
        </div>
        <aside className="card cart-aside" aria-label="Order summary">
          <h2>Summary</h2>
          <CartSummary cart={view} />
        </aside>
      </div>
    </section>
  );
}

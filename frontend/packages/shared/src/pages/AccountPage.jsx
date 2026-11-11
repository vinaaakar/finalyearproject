import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useStore } from '../StoreApp.jsx';
import OrderCard from '../components/OrderCard.jsx';
import AddressCard from '../components/AddressCard.jsx';
import AddressForm from '../components/AddressForm.jsx';
import { ErrorNotice, Field, fieldError, safeNext } from './AuthPages.jsx';

function LoginForm({ next }) {
  const { api, config } = useStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  async function submit(e) {
    e.preventDefault();
    if (inFlight.current) return; // a ref, so a second click/Enter before re-render is ignored too
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      await api.login(email.trim(), password);
    } catch (err) {
      setError(err);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  const withNext = (path) => (next ? `${path}?next=${encodeURIComponent(next)}` : path);
  return (
    <form className="card form" onSubmit={submit} aria-describedby={import.meta.env.DEV ? 'demo-hint' : undefined}>
      <h1>Sign in to {config.name}</h1>
      {next === '/checkout'
        ? <p className="notice notice-info">Sign in to continue to checkout. Your cart is kept.</p>
        : <p className="muted">Sign in to see your orders and let {config.assistantName} check order status for you.</p>}
      <Field id="email" label="Email" error={fieldError(error, 'email')}>
        <input id="email" type="email" autoComplete="email" required maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field id="password" label="Password" error={fieldError(error, 'password')}>
        <input id="password" type="password" autoComplete="current-password" required maxLength={200} value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      <ErrorNotice error={error} inline={['email', 'password']} />
      <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      <p className="form-links">
        New to {config.name}? <Link to={withNext('/register')}>Create an account</Link> · <Link to="/forgot-password">Forgot password?</Link>
      </p>
      {/* Development builds only: production bundles contain no demo credentials (see each app main.jsx). */}
      {import.meta.env.DEV && config.demoEmail && (
        <p id="demo-hint" className="demo-hint">
          Demo account (synthetic): <code>{config.demoEmail}</code> / <code>{config.demoPassword}</code>
        </p>
      )}
    </form>
  );
}

export default function AccountPage() {
  const { api, session } = useStore();
  const [orders, setOrders] = useState({ loading: true, list: [], error: null });
  const [addresses, setAddresses] = useState({ loading: false, list: [], error: null });
  const [editingAddress, setEditingAddress] = useState(null); // null, 'new', or address object
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const next = safeNext(params.get('next'));
  // A confirmation passed by the page that just completed the action (e.g. registration), shown once.
  const [flash] = useState(() => location.state?.flash || null);

  const loadAddresses = useCallback(() => {
    if (!session || session.customer.role === 'agent' || !api.addresses) return;
    setAddresses((prev) => ({ ...prev, loading: true, error: null }));
    api.addresses().then(
      (d) => setAddresses({ loading: false, list: d?.addresses || [], error: null }),
      (e) => setAddresses({ loading: false, list: [], error: e.message })
    );
  }, [api, session]);

  useEffect(() => {
    if (session && next) navigate(next, { replace: true });
  }, [session, next, navigate]);

  useEffect(() => {
    if (!session) return;
    setOrders({ loading: true, list: [], error: null });
    const load = session.customer.role === 'agent' ? api.adminOrders : api.myOrders;
    load().then(
      (d) => setOrders({ loading: false, list: d.orders, error: null }),
      (e) => setOrders({ loading: false, list: [], error: e.message }),
    );
    loadAddresses();
  }, [api, session, loadAddresses]);

  if (!session) return <LoginForm next={next} />;
  const isAgent = session.customer.role === 'agent';

  async function handleSaveAddress(data) {
    if (editingAddress && editingAddress !== 'new' && editingAddress.id) {
      await api.updateAddress(editingAddress.id, data);
    } else {
      await api.createAddress(data);
    }
    setEditingAddress(null);
    loadAddresses();
  }

  async function handleSetDefault(id) {
    await api.setDefaultAddress(id);
    loadAddresses();
  }

  async function handleDelete(id) {
    if (window.confirm('Are you sure you want to delete this address?')) {
      await api.deleteAddress(id);
      loadAddresses();
    }
  }

  return (
    <section className="page-section">
      {flash && <p className="notice notice-ok" role="status">{flash}</p>}
      <div className="account-head">
        <div>
          <h1>{isAgent ? 'Store orders (staff view)' : 'Your orders'}</h1>
          <p className="muted">Signed in as {session.customer.name} ({session.customer.email})</p>
        </div>
        <div className="detail-actions">
          {!isAgent && <Link className="btn" to="/support/requests">My requests</Link>}
          {!isAgent && <Link className="btn" to="/">Continue shopping</Link>}
          {isAgent && <Link className="btn btn-primary" to="/staff/orders">Fulfil orders</Link>}
          <button type="button" className="btn" onClick={() => api.logout()}>Sign out</button>
        </div>
      </div>
      {orders.error && <p className="notice notice-error" role="alert">{orders.error}</p>}
      {orders.loading ? <p className="muted" aria-live="polite">Loading orders…</p> : orders.list.length === 0 ? (
        <div className="empty"><p>No orders yet.</p>{!isAgent && <Link className="btn btn-primary" to="/">Start shopping</Link>}</div>
      ) : (
        <ul className="order-list">
          {orders.list.map((o) => (
            <li key={o.order_number}>
              <OrderCard order={o} showCustomer={isAgent} />
              <Link className="btn btn-small" to={`/orders/${o.order_number}`} aria-label={`View details of order ${o.order_number}`}>View details</Link>{' '}
              {!isAgent && o.awaiting_payment && <Link className="btn btn-primary btn-small" to={`/orders/${o.order_number}/pay`}>Pay now</Link>}
            </li>
          ))}
        </ul>
      )}

      {!isAgent && (
        <div className="account-address-book" style={{ marginTop: '40px' }}>
          <div className="section-head">
            <h2>Address Book</h2>
            {!editingAddress && (
              <button
                type="button"
                className="btn btn-small btn-primary"
                onClick={() => setEditingAddress('new')}
              >
                + Add address
              </button>
            )}
          </div>

          {editingAddress ? (
            <AddressForm
              initial={editingAddress === 'new' ? null : editingAddress}
              onSave={handleSaveAddress}
              onCancel={() => setEditingAddress(null)}
              submitLabel={editingAddress === 'new' ? 'Save address' : 'Update address'}
            />
          ) : addresses.loading ? (
            <p className="muted" aria-live="polite">Loading addresses…</p>
          ) : addresses.error ? (
            <p className="notice notice-error" role="alert">{addresses.error}</p>
          ) : addresses.list.length === 0 ? (
            <div className="card">
              <p className="muted">No saved addresses yet. Save your address to check out faster next time.</p>
              <button
                type="button"
                className="btn btn-small"
                onClick={() => setEditingAddress('new')}
              >
                Add your first address
              </button>
            </div>
          ) : (
            <div className="address-grid">
              {addresses.list.map((addr) => (
                <AddressCard
                  key={addr.id}
                  address={addr}
                  mode="manage"
                  onEdit={(a) => setEditingAddress(a)}
                  onSetDefault={handleSetDefault}
                  onDelete={handleDelete}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

import React, { useEffect, useState } from 'react';
import { useStore } from '../StoreApp.jsx';
import OrderCard from '../components/OrderCard.jsx';

function LoginForm() {
  const { api, config } = useStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(email.trim(), password);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card form" onSubmit={submit} aria-describedby="demo-hint">
      <h1>Sign in to {config.name}</h1>
      <p className="muted">Sign in to see your orders and let the assistant check order status for you.</p>
      <label htmlFor="email">Email</label>
      <input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <label htmlFor="password">Password</label>
      <input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
      {error && <p className="notice notice-error" role="alert">{error}</p>}
      <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      <p id="demo-hint" className="demo-hint">
        Demo account (synthetic): <code>{config.demoEmail}</code> / <code>{config.demoPassword}</code>
      </p>
    </form>
  );
}

export default function AccountPage() {
  const { api, session } = useStore();
  const [orders, setOrders] = useState({ loading: true, list: [], error: null });

  useEffect(() => {
    if (!session) return;
    const load = session.customer.role === 'agent' ? api.adminOrders : api.myOrders;
    load().then(
      (d) => setOrders({ loading: false, list: d.orders, error: null }),
      (e) => setOrders({ loading: false, list: [], error: e.message }),
    );
  }, [api, session]);

  if (!session) return <LoginForm />;
  const isAgent = session.customer.role === 'agent';

  return (
    <section>
      <div className="account-head">
        <div>
          <h1>{isAgent ? 'Store orders (staff view)' : 'Your orders'}</h1>
          <p className="muted">Signed in as {session.customer.name} ({session.customer.email})</p>
        </div>
        <button type="button" className="btn" onClick={api.logout}>Sign out</button>
      </div>
      {orders.error && <p className="notice notice-error" role="alert">{orders.error}</p>}
      {orders.loading ? <p className="muted">Loading orders…</p> : orders.list.length === 0 ? (
        <p className="empty">No orders yet.</p>
      ) : (
        <ul className="order-list">
          {orders.list.map((o) => <li key={o.order_number}><OrderCard order={o} showCustomer={isAgent} /></li>)}
        </ul>
      )}
    </section>
  );
}

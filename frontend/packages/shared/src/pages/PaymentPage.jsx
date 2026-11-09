import React, { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useStore } from '../StoreApp.jsx';
import OrderCard from '../components/OrderCard.jsx';

// Sandbox payment step. No card details are collected anywhere. The two "simulate" buttons stand in
// for a payment provider's hosted page; the order only changes after the SERVER asks the provider.
export default function PaymentPage() {
  const { number } = useParams();
  const { api, session } = useStore();
  const [order, setOrder] = useState(null);
  const [payment, setPayment] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [o, p] = await Promise.all([api.order(number), api.paymentStatus(number)]);
      setOrder(o.order);
      setPayment(p.payment);
    } catch (e) {
      setError(e.message);
    }
  }, [api, number]);

  useEffect(() => {
    if (session) load();
  }, [session, load]);

  async function run(fn) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const start = () => run(async () => setPayment((await api.startPayment(number)).payment));
  const simulate = (outcome) => run(async () => {
    await api.completeSandboxPayment(payment.reference, outcome);
    const r = await api.verifyPayment(number);
    setOrder(r.order);
    setPayment(r.payment);
  });
  const cancel = () => run(async () => setOrder((await api.cancelOrder(number)).order));

  if (!session) return <div className="card form"><p>Please <Link to="/account">sign in</Link> to see this order.</p></div>;
  if (!order) return error ? <p className="notice notice-error" role="alert">{error}</p> : <p className="muted" aria-live="polite">Loading…</p>;

  const awaiting = order.status === 'pending_payment';
  const inFlight = payment?.status === 'pending';

  return (
    <section className="page-section narrow">
      <h1>{awaiting ? 'Payment' : order.status === 'cancelled' ? 'Order cancelled' : 'Thank you!'}</h1>
      <p className="sandbox-banner" role="note">
        <strong>TEST MODE.</strong> Payments use a sandbox provider. No real money moves and no card details are collected.
      </p>
      <OrderCard order={order} />
      {error && <p className="notice notice-error" role="alert">{error}</p>}

      {awaiting && (
        <div className="card pay-card">
          {payment?.status === 'failed' && <p className="notice notice-error" role="status">The test payment was declined. You can try again.</p>}
          {!inFlight ? (
            <button type="button" className="btn btn-primary" onClick={start} disabled={busy}>Pay {order.total} (test)</button>
          ) : (
            <>
              <p>Sandbox payment {payment.reference.slice(0, 12)}… for {payment.amount}. Choose the simulated result:</p>
              <div className="detail-actions">
                <button type="button" className="btn btn-primary" onClick={() => simulate('success')} disabled={busy}>Simulate approved payment</button>
                <button type="button" className="btn" onClick={() => simulate('decline')} disabled={busy}>Simulate declined payment</button>
              </div>
            </>
          )}
          <button type="button" className="btn btn-small link-btn" onClick={cancel} disabled={busy}>Cancel this order</button>
        </div>
      )}
      {order.status === 'processing' && payment?.status === 'succeeded' && (
        <p className="notice notice-ok" role="status">Payment confirmed by the (sandbox) payment provider. Your order is being prepared.</p>
      )}
      <p><Link to="/account">View all orders</Link> · <Link to="/">Continue shopping</Link></p>
    </section>
  );
}

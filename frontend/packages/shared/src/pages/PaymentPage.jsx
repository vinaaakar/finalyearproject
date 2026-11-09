import React, { useCallback, useEffect, useRef, useState } from 'react';
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
  // Cancelling is consequential: first explain what will happen, then cancel only on an explicit second click.
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const cancelling = useRef(false);

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
  const cancel = async () => {
    if (cancelling.current) return;          // ignore double clicks while the request is in flight
    cancelling.current = true;
    try {
      await run(async () => {
        const r = await api.cancelOrder(number);
        // Report success only when the server says the order is now cancelled.
        if (r.order?.status !== 'cancelled') throw new Error('The order could not be cancelled. Please try again or contact support.');
        setOrder(r.order);
        setCancelled(true);
        setConfirmCancel(false);
      });
    } finally {
      cancelling.current = false;
    }
  };

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
          {!confirmCancel ? (
            <button type="button" className="btn btn-small link-btn" onClick={() => setConfirmCancel(true)} disabled={busy}>Cancel this order</button>
          ) : (
            <div className="notice notice-warn" role="group" aria-label={`Confirm cancelling order ${order.order_number}`}>
              <p>
                <strong>Cancel order {order.order_number}?</strong> The order will be cancelled and its items released.
                {' '}No payment has been taken for it{inFlight ? ', and the test payment in progress will be cancelled too' : ''}.
                {' '}This can’t be undone.
              </p>
              <div className="detail-actions">
                <button type="button" className="btn btn-danger" onClick={cancel} disabled={busy}>
                  {busy ? 'Cancelling…' : `Yes, cancel order ${order.order_number}`}
                </button>
                <button type="button" className="btn" onClick={() => setConfirmCancel(false)} disabled={busy}>Keep my order</button>
              </div>
            </div>
          )}
        </div>
      )}
      {cancelled && order.status === 'cancelled' && (
        <p className="notice notice-ok" role="status">Order {order.order_number} has been cancelled. No payment was taken.</p>
      )}
      {order.status === 'processing' && payment?.status === 'succeeded' && (
        <p className="notice notice-ok" role="status">Payment confirmed by the (sandbox) payment provider. Your order is being prepared.</p>
      )}
      <p><Link to="/account">View all orders</Link> · <Link to="/">Continue shopping</Link></p>
    </section>
  );
}

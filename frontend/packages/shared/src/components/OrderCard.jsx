import React from 'react';

export default function OrderCard({ order, showCustomer = false }) {
  return (
    <div className="order-card">
      <div className="order-top">
        <strong>{order.order_number}</strong>
        <span className={`status status-${order.status}`}>{order.status_label}</span>
      </div>
      {showCustomer && order.customer_name && <p className="muted">{order.customer_name}</p>}
      {order.items?.length > 0 && (
        <p className="order-items">{order.items.map((i) => `${i.quantity}× ${i.name}`).join(', ')}</p>
      )}
      <p className="order-meta">
        Total {order.total}
        {order.estimated_delivery && ['processing', 'shipped', 'out_for_delivery'].includes(order.status) && <> · Expected {order.estimated_delivery}</>}
        {order.carrier && order.tracking_number && <> · {order.carrier} {order.tracking_number}</>}
      </p>
    </div>
  );
}

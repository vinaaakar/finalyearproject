import React from 'react';
import { Link } from 'react-router-dom';

export function StockBadge({ product }) {
  if (!product.in_stock) return <span className="badge badge-out">Out of stock</span>;
  if (product.stock_qty <= 5) return <span className="badge badge-low">Only {product.stock_qty} left</span>;
  return <span className="badge badge-in">In stock</span>;
}

export default function ProductCard({ product, compact = false }) {
  return (
    <Link to={`/products/${product.slug}`} className={`product-card ${compact ? 'product-card-compact' : ''}`}>
      <span className="product-art" aria-hidden="true">{product.emoji}</span>
      <span className="product-body">
        <span className="product-category">{product.category}</span>
        <span className="product-name">{product.name}</span>
        <span className="product-meta">
          <span className="price">{product.price}</span>
          <StockBadge product={product} />
        </span>
      </span>
    </Link>
  );
}

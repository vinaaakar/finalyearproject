import React from 'react';
import { useStore } from '../StoreApp.jsx';

// One image slot for a product, used everywhere a product appears. Order of preference:
// a real photo from config.productImages, the store's own illustration (config.art), or a plain
// named placeholder. Images are decorative next to the product name, except on the detail page.
export default function ProductImage({ product, size = 'card', label = false }) {
  const { config } = useStore();
  const photo = config.productImages?.[product.slug];
  const Art = config.art?.[product.slug];
  const a11y = label ? { role: 'img', 'aria-label': `${photo ? 'Photo' : 'Illustration'} of ${product.name}` } : { 'aria-hidden': true };
  return (
    <span className={`product-image product-image-${size}`} {...a11y}>
      {photo ? <img src={photo} alt="" loading="lazy" decoding="async" /> : Art ? <Art /> : <Placeholder name={product.name} />}
    </span>
  );
}

function Placeholder({ name }) {
  const initials = name.split(/\s+/).filter((w) => /^[A-Za-z]/.test(w)).slice(0, 2).map((w) => w[0].toUpperCase()).join('');
  return (
    <span className="product-placeholder">
      <span className="product-placeholder-mark">{initials}</span>
      <span className="product-placeholder-name">{name}</span>
    </span>
  );
}

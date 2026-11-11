// India-only storefront: every price is shown in Indian rupees (₹), from the store's approved INR price list (the server
// sends it as product.prices.INR / product.price). Nothing here converts or relabels an amount: a product without an
// approved INR price shows "Price in ₹ not set yet" and can't be ordered.
export const DELIVERY_COUNTRY = 'IN';
export const CURRENCY = 'INR';
export const NOT_SET = 'Price in ₹ not set yet';

/** { text, available } for a product's price in ₹. */
export function productPrice(product) {
  if (product.prices) {
    const p = product.prices[CURRENCY];
    return p ? { text: p.display, available: true } : { text: NOT_SET, available: false };
  }
  // A product summary (e.g. a chat card) carries its own price and currency.
  return product.currency === CURRENCY && product.price ? { text: product.price, available: true } : { text: NOT_SET, available: false };
}

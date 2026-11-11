-- Currency by delivery country (India = INR, US = the store's USD catalogue). Additive only.
--   * product_prices: owner-APPROVED prices in another currency (INR). Empty until the owner approves a list; there is
--                     no conversion anywhere — a product without an approved INR price simply has no INR price.
--   * orders.currency: the currency an order's amounts are in. Every existing order was placed in the store currency
--                      (USD for both stores), which the default records; no stored amount changes.
-- Down: down/0008_price_lists.down.sql.
CREATE TABLE product_prices (
    product_id   INTEGER NOT NULL REFERENCES products (id),
    currency     CHAR(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    price_minor  INTEGER NOT NULL CHECK (price_minor >= 0),
    approved_by  TEXT NOT NULL CHECK (length(approved_by) BETWEEN 1 AND 100),
    approved_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, currency)
);

ALTER TABLE orders ADD COLUMN currency CHAR(3) NOT NULL DEFAULT 'USD' CHECK (currency ~ '^[A-Z]{3}$');

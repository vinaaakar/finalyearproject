-- Cart, checkout, accounts (sessions + password reset) and payments.
-- Applied identically to each store's own database, like 0001.

-- Shipping pricing used by the server to compute totals (must match the shipping policy text).
ALTER TABLE store_profile
    ADD COLUMN standard_shipping_cents  INTEGER NOT NULL DEFAULT 0 CHECK (standard_shipping_cents >= 0),
    ADD COLUMN free_shipping_min_cents  INTEGER CHECK (free_shipping_min_cents >= 0),
    ADD COLUMN expedited_shipping_cents INTEGER CHECK (expedited_shipping_cents >= 0);

-- ---- accounts ------------------------------------------------------------------------------
-- Emails are unique per store regardless of case (registration stores them lower-cased).
CREATE UNIQUE INDEX customers_email_lower_idx ON customers (lower(email));

-- Every issued access token references one session row, so sign-out and password
-- resets can revoke tokens before they expire. Only a hash of the session id is stored.
CREATE TABLE sessions (
    id_hash      TEXT PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers (id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL,
    revoked_at   TIMESTAMPTZ
);
CREATE INDEX sessions_customer_idx ON sessions (customer_id);

CREATE TABLE password_reset_tokens (
    id           SERIAL PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers (id) ON DELETE CASCADE,
    token_hash   TEXT NOT NULL UNIQUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL,
    used_at      TIMESTAMPTZ
);
CREATE INDEX password_reset_customer_idx ON password_reset_tokens (customer_id);

-- ---- cart ----------------------------------------------------------------------------------
-- A cart belongs to a signed-in customer, or to a guest who holds a random cart token
-- (only its hash is stored). Prices are never stored in the cart: they are read from
-- `products` every time totals are computed.
CREATE TABLE carts (
    id           SERIAL PRIMARY KEY,
    customer_id  INTEGER REFERENCES customers (id) ON DELETE CASCADE,
    guest_token_hash TEXT UNIQUE,
    status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'converted', 'merged')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (customer_id IS NOT NULL OR guest_token_hash IS NOT NULL)
);
-- At most one open cart per customer.
CREATE UNIQUE INDEX carts_one_open_per_customer ON carts (customer_id) WHERE status = 'open' AND customer_id IS NOT NULL;

CREATE TABLE cart_items (
    cart_id     INTEGER NOT NULL REFERENCES carts (id) ON DELETE CASCADE,
    product_id  INTEGER NOT NULL REFERENCES products (id),
    quantity    INTEGER NOT NULL CHECK (quantity > 0 AND quantity <= 10),
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (cart_id, product_id)
);

-- ---- orders --------------------------------------------------------------------------------
ALTER TABLE orders DROP CONSTRAINT orders_status_check;
ALTER TABLE orders ADD CONSTRAINT orders_status_check CHECK (status IN (
    'pending_payment', 'processing', 'shipped', 'out_for_delivery', 'delivered', 'cancelled', 'returned'));

ALTER TABLE orders
    ADD COLUMN idempotency_key   TEXT,
    ADD COLUMN subtotal_cents    INTEGER CHECK (subtotal_cents >= 0),
    ADD COLUMN shipping_cents    INTEGER CHECK (shipping_cents >= 0),
    ADD COLUMN shipping_method   TEXT CHECK (shipping_method IN ('standard', 'expedited')),
    ADD COLUMN shipping_name     TEXT,
    ADD COLUMN shipping_line1    TEXT,
    ADD COLUMN shipping_line2    TEXT,
    ADD COLUMN shipping_city     TEXT,
    ADD COLUMN shipping_region   TEXT,
    ADD COLUMN shipping_country  CHAR(2);
-- Repeated submissions with the same key return the existing order instead of creating another.
CREATE UNIQUE INDEX orders_customer_idempotency ON orders (customer_id, idempotency_key) WHERE idempotency_key IS NOT NULL;

-- New order numbers (seeded demo orders use lower numbers).
CREATE SEQUENCE order_number_seq START 50001 MAXVALUE 99999;

-- ---- payments ------------------------------------------------------------------------------
CREATE TABLE payments (
    id            SERIAL PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES orders (id),
    provider      TEXT NOT NULL,
    provider_ref  TEXT NOT NULL UNIQUE,
    amount_cents  INTEGER NOT NULL CHECK (amount_cents >= 0),
    currency      CHAR(3) NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('pending', 'succeeded', 'failed', 'cancelled')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX payments_order_idx ON payments (order_id);
-- Only one payment attempt per order can be in flight or successful at a time.
CREATE UNIQUE INDEX payments_one_active_per_order ON payments (order_id) WHERE status IN ('pending', 'succeeded');

-- State kept by the SANDBOX payment provider (stands in for a remote provider's records).
-- No card data exists anywhere: the sandbox only knows an amount and an outcome.
CREATE TABLE sandbox_payment_intents (
    ref           TEXT PRIMARY KEY,
    amount_cents  INTEGER NOT NULL,
    currency      CHAR(3) NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('requires_action', 'succeeded', 'declined', 'cancelled')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

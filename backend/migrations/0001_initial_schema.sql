-- Applied identically to each store's own database. No table holds a store_id:
-- isolation is by physical database + database role, not by a column filter.

CREATE TABLE store_profile (
    id              SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    name            TEXT NOT NULL,
    support_email   TEXT NOT NULL,
    support_hours   TEXT NOT NULL,
    currency        CHAR(3) NOT NULL DEFAULT 'USD'
);

CREATE TABLE policies (
    topic       TEXT PRIMARY KEY CHECK (topic IN ('shipping', 'returns', 'warranty', 'payment')),
    summary     TEXT NOT NULL,
    details     TEXT NOT NULL
);

CREATE TABLE products (
    id              SERIAL PRIMARY KEY,
    sku             TEXT NOT NULL UNIQUE,
    slug            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,
    description     TEXT NOT NULL,
    price_cents     INTEGER NOT NULL CHECK (price_cents >= 0),
    stock_qty       INTEGER NOT NULL CHECK (stock_qty >= 0),
    emoji           TEXT NOT NULL DEFAULT '🛍️',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX products_category_idx ON products (category);

CREATE TABLE customers (
    id              SERIAL PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    full_name       TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'customer' CHECK (role IN ('customer', 'agent')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE orders (
    id                  SERIAL PRIMARY KEY,
    order_number        TEXT NOT NULL UNIQUE,
    customer_id         INTEGER NOT NULL REFERENCES customers (id),
    status              TEXT NOT NULL CHECK (status IN ('processing', 'shipped', 'out_for_delivery', 'delivered', 'cancelled', 'returned')),
    shipping_postal_code TEXT NOT NULL,
    carrier             TEXT,
    tracking_number     TEXT,
    estimated_delivery  DATE,
    total_cents         INTEGER NOT NULL CHECK (total_cents >= 0),
    placed_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX orders_customer_idx ON orders (customer_id);

CREATE TABLE order_items (
    id              SERIAL PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    product_id      INTEGER NOT NULL REFERENCES products (id),
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0)
);
CREATE INDEX order_items_order_idx ON order_items (order_id);

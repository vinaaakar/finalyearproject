-- Saved customer addresses (Amazon-style address book).
-- Additive only: no existing table, column, row or constraint is changed.
-- Applied identically to each store's database; isolation is physical (separate DBs per store).

CREATE TABLE customer_addresses (
    id           SERIAL PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers (id) ON DELETE CASCADE,
    label        TEXT NOT NULL DEFAULT 'Home' CHECK (length(label) BETWEEN 1 AND 50),
    full_name    TEXT NOT NULL CHECK (length(full_name) BETWEEN 1 AND 100),
    line1        TEXT NOT NULL CHECK (length(line1) BETWEEN 1 AND 120),
    line2        TEXT CHECK (line2 IS NULL OR length(line2) <= 120),
    city         TEXT NOT NULL CHECK (length(city) BETWEEN 1 AND 80),
    region       TEXT NOT NULL CHECK (region ~ '^[A-Za-z]{2}$'),
    postal_code  TEXT NOT NULL CHECK (postal_code ~ '^\d{5}(-\d{4})?$|^\d{6}$'),
    country      CHAR(2) NOT NULL DEFAULT 'IN' CHECK (country IN ('IN', 'US')),
    phone        TEXT CHECK (phone IS NULL OR phone ~ '^\+[1-9][0-9]{7,14}$'),
    is_default   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX customer_addresses_customer_idx ON customer_addresses (customer_id);
CREATE UNIQUE INDEX customer_addresses_one_default ON customer_addresses (customer_id) WHERE is_default = TRUE;

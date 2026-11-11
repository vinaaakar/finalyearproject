-- Phase F: order fulfilment. Additive only (expand): no existing column, row or constraint is changed or removed,
-- so code from before this migration keeps working against it.
--   * orders.tracking_url        — carrier tracking link entered by staff (https only)
--   * orders.shipped_at / delivered_at — when staff recorded those steps
--   * order_status_history       — every status change from now on: from → to, who (customer / staff / system), note,
--                                  and the carrier/tracking recorded with a shipment. Existing orders have no history
--                                  rows (their earlier changes were never recorded); nothing is back-filled or guessed.
-- Down: down/0005_fulfilment.down.sql (refuses if history or tracking data would be lost unless explicitly forced).

ALTER TABLE orders
    ADD COLUMN tracking_url  TEXT CHECK (tracking_url IS NULL OR (tracking_url ~ '^https://[^\s]+$' AND length(tracking_url) <= 300)),
    ADD COLUMN shipped_at    TIMESTAMPTZ,
    ADD COLUMN delivered_at  TIMESTAMPTZ;

CREATE TABLE order_status_history (
    id                 SERIAL PRIMARY KEY,
    order_id           INTEGER NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    from_status        TEXT,                 -- NULL for the "order placed" event
    to_status          TEXT NOT NULL,
    actor_role         TEXT NOT NULL CHECK (actor_role IN ('customer', 'agent', 'system')),
    actor_customer_id  INTEGER REFERENCES customers (id),   -- the customer or staff account; NULL for system events
    note               TEXT CHECK (note IS NULL OR length(note) <= 500),
    carrier            TEXT,
    tracking_number    TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((actor_role = 'system') = (actor_customer_id IS NULL))
);
CREATE INDEX order_status_history_order_idx ON order_status_history (order_id, created_at);

-- Customer-care requests: complaints, return requests, SIMULATED refund requests and human-help (escalation) requests,
-- each with an auditable history. Additive only: no existing table, column, row or constraint is changed.
--   * care_requests        — one row per request; the store is the database itself (each store has its own), and the
--                            reference carries the store prefix (SA-… / BB-…). Customer, order and item are validated by
--                            the application against the signed-in customer before insert (app/care_requests.py).
--   * care_request_events  — every status change, staff assignment, internal staff note and customer-visible message.
--                            visibility = 'internal' rows are never returned to customers.
-- Refunds are a simulated academic workflow: nothing here moves money or calls a payment provider.
-- Down: down/0009_care_requests.down.sql.
CREATE SEQUENCE care_request_seq START 1;

CREATE TABLE care_requests (
    id               SERIAL PRIMARY KEY,
    reference        TEXT NOT NULL UNIQUE CHECK (reference ~ '^[A-Z]{2}-(CMP|RET|RFD|ESC)-[0-9]{5,}$'),
    kind             TEXT NOT NULL CHECK (kind IN ('complaint', 'return', 'refund', 'escalation')),
    customer_id      INTEGER NOT NULL REFERENCES customers (id),
    order_id         INTEGER REFERENCES orders (id),
    order_item_id    INTEGER REFERENCES order_items (id),
    category         TEXT NOT NULL CHECK (category ~ '^[a-z_]{2,40}$'),
    description      TEXT NOT NULL CHECK (length(description) BETWEEN 1 AND 1000),
    status           TEXT NOT NULL CHECK (status IN ('open', 'requested', 'under_review', 'awaiting_customer', 'assigned',
                                                     'in_progress', 'approved', 'rejected', 'received', 'inspected', 'completed',
                                                     'simulated_completed', 'resolved', 'closed', 'withdrawn')),
    assigned_to      INTEGER REFERENCES customers (id),          -- a staff (agent) account of this store
    idempotency_key  TEXT CHECK (idempotency_key IS NULL OR idempotency_key ~ '^[A-Za-z0-9_-]{16,64}$'),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at      TIMESTAMPTZ,
    CHECK (order_item_id IS NULL OR order_id IS NOT NULL),
    CHECK (kind IN ('complaint', 'escalation') OR order_id IS NOT NULL),     -- returns and refunds are about an order
    UNIQUE (customer_id, idempotency_key)
);
-- At most one OPEN request of a kind for the same order item (or whole order): a double submission or a repeat request
-- while one is still being handled is refused (the application returns the existing reference).
CREATE UNIQUE INDEX care_requests_one_open_per_item ON care_requests (kind, order_id, coalesce(order_item_id, 0))
    WHERE order_id IS NOT NULL
      AND status NOT IN ('rejected', 'completed', 'simulated_completed', 'resolved', 'closed', 'withdrawn');
CREATE INDEX care_requests_queue_idx ON care_requests (kind, status, created_at DESC);
CREATE INDEX care_requests_customer_idx ON care_requests (customer_id, created_at DESC);
CREATE INDEX care_requests_order_idx ON care_requests (order_id);

CREATE TABLE care_request_events (
    id                 SERIAL PRIMARY KEY,
    request_id         INTEGER NOT NULL REFERENCES care_requests (id),
    event              TEXT NOT NULL CHECK (event IN ('created', 'status', 'assigned', 'note', 'message', 'customer_reply')),
    from_status        TEXT,
    to_status          TEXT,
    visibility         TEXT NOT NULL CHECK (visibility IN ('customer', 'internal')),
    body               TEXT CHECK (body IS NULL OR length(body) BETWEEN 1 AND 1000),
    actor_role         TEXT NOT NULL CHECK (actor_role IN ('customer', 'agent', 'system')),
    actor_customer_id  INTEGER REFERENCES customers (id),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((actor_role = 'system') = (actor_customer_id IS NULL)),
    CHECK (event <> 'note' OR visibility = 'internal')
);
CREATE INDEX care_request_events_request_idx ON care_request_events (request_id, created_at);

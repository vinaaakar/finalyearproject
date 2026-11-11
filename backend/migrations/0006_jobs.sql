-- Phase G: background work, stored in each store's own database (docs/scheduler-architecture.md). Additive only.
--   * job_runs — one row per periodic job: last start / success / error, run and failure counts (observability).
--   * outbox   — durable queue of side effects (e-mails) written in the SAME transaction as the change that causes
--                them, processed by `python -m app.worker` with leases, retries with backoff and a dead state.
--                Payloads hold references (an order number), never message bodies or e-mail addresses.
-- Down: down/0006_jobs.down.sql.

CREATE TABLE job_runs (
    job                TEXT PRIMARY KEY,
    last_started_at    TIMESTAMPTZ,
    last_succeeded_at  TIMESTAMPTZ,
    last_error         TEXT,
    last_error_at      TIMESTAMPTZ,
    last_summary       JSONB,
    runs               INTEGER NOT NULL DEFAULT 0,
    failures           INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE outbox (
    id            BIGSERIAL PRIMARY KEY,
    kind          TEXT NOT NULL CHECK (kind ~ '^[a-z_]+\.[a-z_]+$'),
    dedupe_key    TEXT NOT NULL UNIQUE,                 -- the same event is queued at most once
    payload       JSONB NOT NULL DEFAULT '{}'::jsonb,
    status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'dead')),
    attempts      INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    available_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_until  TIMESTAMPTZ,
    last_error    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at  TIMESTAMPTZ
);
CREATE INDEX outbox_ready_idx ON outbox (available_at, id) WHERE status = 'pending';

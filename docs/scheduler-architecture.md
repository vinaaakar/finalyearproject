# Scheduler architecture for reconciliation, unpaid-order expiry and outbox work

Status: **worker implemented in Phase G** (`backend/app/worker.py`, migration `0006_jobs.sql`, tests
`backend/tests/test_phaseG_worker.py`). Jobs today: `expire_unpaid` (cancels unpaid orders after
`UNPAID_ORDER_TTL_MINUTES`, default 1440, after checking the payment provider) and the outbox (`email.order_shipped`).
Payment reconciliation/capture/refund jobs below remain designs (payment integration is out of scope). The worker is not
started by any script; run `backend/.venv/bin/python -m app.worker` (or `--once`) by hand. Original decision text: It selects how the periodic and background
work in `docs/india-razorpay-design.md` §7.3–7.7 will run: payment reconciliation (every 10 min), unpaid-order expiry,
capturing authorisations before their window ends, sending refunds, and processing the `outbox` (emails, staff alerts).

## Requirements
1. **Correct under duplicates:** two runs of the same job at once must not double-capture, double-refund or double-cancel.
   (The handlers are idempotent and use row locks, but the scheduler should still avoid concurrent runs.)
2. **Survives restarts:** queued work is not lost when a process restarts; a job interrupted mid-way is safe to rerun.
3. **Never slows the API:** the webhook must answer well within Razorpay's 5-second limit; slow work runs elsewhere.
4. **Observable:** last successful run per job, failures, and a stale-job alert (reconciliation is mandatory, so a stopped
   scheduler is an incident).
5. **Retries with backoff** and a dead-letter state with an alert.
6. **Two stores:** each store database has its own `outbox` and `job_runs`; the scheduler serves both and never mixes them.
7. **No new dependencies** unless justified (psycopg and the standard library are enough).

## Options compared

| Criterion | 1. In-process scheduler (thread/async loop inside the API) | 2. System cron / launchd | 3. Dedicated background worker process | 4. Database-backed job queue (outbox + leases) |
|---|---|---|---|---|
| Reliability | Dies with every API restart (`restart_api.sh`); a crash loses in-flight work | Reliable trigger, but each run is a cold start; missed runs while the machine sleeps (macOS) | Good: long-running, supervised, restarts on failure | Work is durable in PostgreSQL; survives any process restart |
| Duplicate prevention | Every API instance runs its own copy → duplicates | Duplicates if a run overlaps the next or two hosts have the crontab | Needs a lock if more than one worker runs | `FOR UPDATE SKIP LOCKED` claims + leases; periodic jobs take an advisory lock |
| Restart behaviour | Lost schedule state; jobs restart from scratch | Stateless | Resumes; interrupted rows released by lease expiry | Unprocessed rows wait; expired leases are reclaimed |
| Multi-instance safety | Unsafe without extra locking | Unsafe across hosts | Safe with advisory locks | Safe by design |
| Operational complexity | Lowest to write, hardest to reason about | Low; per-host configuration | Medium: one more process to run and monitor | Low once the tables exist (they are already in the 0006 design) |
| Monitoring | Hidden inside API logs | Cron mail/logs only | Own logs + `job_runs` | `outbox` counts, ages, dead rows; `job_runs` |
| Retry behaviour | Ad hoc | None (next run) | Implemented in the worker | `attempts`, `available_at` backoff, `dead` status |
| Resource use (local M4) | Shares the API process | Negligible | One idle Python process (~40–60 MB RSS), polling every few seconds with tiny indexed queries | No extra process by itself; it is a storage pattern used by option 3 |
| Production suitability | Poor (competes with request handling, duplicates on scale-out) | Acceptable only as a trigger | Good | Good |
| New dependencies | None (APScheduler would be one) | None | None | None |

Options 3 and 4 are complementary: the **queue** (4) holds the work durably; the **worker** (3) executes it and runs the
periodic jobs.

## Decision

**Recommended: a dedicated worker process (`python -m app.worker`, to be written in Phase 2) over the PostgreSQL-backed
outbox and `job_runs` tables defined in migration 0006.**

| Environment | Setup |
|---|---|
| Local development (this M4) | Run the worker by hand in its own terminal when testing payments (`backend/.venv/bin/python -m app.worker --store all`), or not at all when payments aren't being exercised. It is **not** added to `scripts/start.sh` until approved, and `scripts/restart_api.sh` never touches it. Because work is in the database, stopping it loses nothing. |
| Initial single-instance production | One worker process supervised by the host (systemd unit or a second container with restart policy), separate from the API process. Same code, same database. |
| Future multi-instance production | Any number of worker processes: outbox rows claimed with `SELECT … FOR UPDATE SKIP LOCKED` plus a lease (`locked_until`); each periodic job runs under `pg_try_advisory_lock(<job key>)` per store database, so exactly one instance runs it at a time. A Redis/Celery-style queue is only worth adding if volume outgrows PostgreSQL, which is far beyond these stores. |

Rejected: **in-process** (API restarts and scale-out make it unreliable, and it competes with webhook latency);
**cron alone** (no retries, no durable queue, duplicate risk; it may still be used as an external *trigger* that runs
`python -m app.worker --once` if a host offers no process supervision).

## Worker behaviour (design)

```
loop every 5 s (configurable), for each store database:
    # periodic jobs, at most one runner across all instances
    for job, interval in [("reconcile", 10 min), ("expire_unpaid", 5 min), ("capture_before_window", 5 min)]:
        if due(job_runs[job], interval) and pg_try_advisory_lock(key(job)):
            UPDATE job_runs SET last_started = now() …
            run job in short per-order transactions (row locks as in RZP §7.5–7.6); each order is independent
            UPDATE job_runs SET last_succeeded = now() (or last_error, last_error_at)
            pg_advisory_unlock(key(job))
    # outbox
    claim up to N rows: UPDATE outbox SET locked_until = now() + 2 min, attempts = attempts + 1
                        WHERE id IN (SELECT id FROM outbox WHERE status = 'pending' AND available_at <= now()
                                     AND (locked_until IS NULL OR locked_until < now())
                                     ORDER BY id FOR UPDATE SKIP LOCKED LIMIT N) RETURNING *
    for each row: run its handler (idempotent; e.g. refund send uses the deterministic receipt, RZP §7.7)
        success → status = 'done', processed_at = now()
        failure → last_error; available_at = now() + min(2^attempts minutes, 6 h); after 10 attempts → status = 'dead' + alert
```
- **Restart / crash:** a row whose worker died is reclaimed after `locked_until`; its handler is idempotent, so a repeat is
  safe. Periodic jobs hold session advisory locks, released automatically when the process dies.
- **Shutdown:** on SIGTERM finish the current row, release locks, exit.
- **Health:** the API's `/api/health` (or an admin endpoint) reports, per store, `job_runs` ages and counts of pending/dead
  outbox rows. **Alerts:** reconcile not successful for 30 min; any `dead` row; outbox oldest pending > 15 min; Razorpay
  "webhook disabled" email (RZP §7.4).
- **Security:** the worker uses the same per-store database roles and `.env`; it exposes no network port.

## Tests (see `docs/testing-plan.md`)
Two workers claim the same outbox rows → each row processed once; periodic job lock held → second instance skips; worker
killed mid-row → row reclaimed after the lease and processed once; backoff schedule and `dead` after max attempts;
`job_runs` updated on success and failure; stale-job health signal.

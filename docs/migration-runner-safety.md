# Migration runner safety (F14): design

Status: **design only. `backend/app/migrate.py` is unchanged; nothing here is implemented or executed.** Implementing it
changes the `schema_migrations` bookkeeping table, so the first run of the new runner is itself a reviewed, approved step
(§6). Related: `docs/database-safety.md` (backup, restore-check, recovery), `docs/india-razorpay-design.md` §4 (how
0004–0007 will be applied), `docs/testing-plan.md` (Migration safety tests).

## 1. Current behaviour (`backend/app/migrate.py`)

| Lines | Behaviour |
|---|---|
| 17 | Migrations are `backend/migrations/*.sql` (top level only; `down/` is never read — tested in `scripts/tests/test_dbsafety.py`) |
| 24 | Creates `schema_migrations (version PRIMARY KEY, applied_at)` if missing |
| 25–30 | Applies files not yet recorded, in filename order |
| 31–33 | Each migration runs **in one transaction together with its version row**: a failing migration leaves that store unchanged |
| 38–41 | `migrate_all` applies **every** pending migration to Store A, then **every** pending migration to Store B |
| — | `tests/conftest.py` calls `migrate_database(url)` directly for the `*_test` databases; `scripts/test.sh` relies on that |

## 2. Weaknesses

| # | Weakness | Consequence |
|---|---|---|
| W1 | No checksum of applied files | Editing an already-applied migration goes unnoticed; a fresh database built from the edited file differs from existing ones |
| W2 | No concurrency lock | Two runs at once (two terminals, a deploy plus a manual run) race; one fails midway or both attempt the same DDL |
| W3 | Precheck not enforced | The runner will migrate without a recent verified backup or when the two stores are already at different versions |
| W4 | Store-by-store ordering (line 39) | If Store B fails, Store A may be several versions ahead, not one |
| W5 | Thin diagnostics | Only a printed summary; no per-version timing, no record of a failed run, no lock-holder information |
| W6 | Unbounded waits | DDL waits indefinitely for locks held by the live API, which can block customer requests behind it |

## 3. Design

### 3.1 Checksums (W1)
- `schema_migrations` gains `checksum TEXT` (SHA-256 hex of the file's **exact bytes**, no normalisation: even a whitespace
  or line-ending change counts as a modification) and `applied_by TEXT` (`application_name` + host).
- The version row and its checksum are inserted **in the same transaction as the migration SQL** (as today for the
  version), so a version can never be recorded without its checksum or vice versa.
- Every run, before doing anything, compares each recorded version's checksum with the file on disk, for **both** stores:
  - recorded version whose file is missing → **refuse**;
  - checksum differs → **refuse**, listing version, recorded hash, file hash, and `git log -- <file>` hint;
  - recorded checksum is `NULL` (rows from before this change) → refuse until adopted (§6).
- Files are linted before use and refused if they contain transaction control (`BEGIN`, `COMMIT`, `ROLLBACK`, `SAVEPOINT`) or
  statements that cannot run inside a transaction (`CREATE INDEX CONCURRENTLY`, `VACUUM`, `ALTER SYSTEM`), because they would
  break the one-transaction-per-migration guarantee.

### 3.2 Concurrency lock (W2)
- The runner connects to **both** store databases with `application_name = 'avc-migrate'` and takes a **session-level
  advisory lock** in each, always in the same order (Store A, then Store B): `pg_try_advisory_lock(<fixed 64-bit key>)`,
  retried every 500 ms until `--lock-timeout` (default 30 s). A session lock is released automatically if the process dies,
  so a crash never leaves the databases locked.
- On timeout: refuse with a diagnostic naming the holder (`SELECT pid, application_name, backend_start, client_addr FROM
  pg_stat_activity JOIN pg_locks USING (pid) WHERE locktype = 'advisory'`). Never steal or terminate the holder.
- Inside each migration transaction: `SET LOCAL lock_timeout = '5s'` and `SET LOCAL statement_timeout = '5min'` (tunable),
  so a migration that cannot get its table lock fails cleanly instead of queueing customer requests behind it (W6). A
  timeout rolls that migration back; the run stops (§3.4).

### 3.3 Enforced precheck (W3)
Before taking the advisory locks' first write, the runner runs the same checks as `scripts/dbsafety.py precheck` and
**refuses** unless all pass:
- container healthy; both stores reachable; both stores at the **same** applied versions with valid checksums;
- a backup that verifies (checksums, TOC, row counts) and is younger than `--max-backup-age` (default 24 h), covering both
  stores; the operator passes it explicitly: `--backup backups/db-<ts>`;
- the pending list is identical for both stores.
Exception: databases whose name ends in `_test` (used by `tests/conftest.py`) skip the backup requirement only; there is no
override flag for any other database.

### 3.4 Two-store ordering, failure and recovery (W4)
- **Lockstep:** for each pending version V (in order): apply V to Store A in one transaction, then V to Store B in one
  transaction; only then move to V+1. A failure can therefore leave the stores at most **one version** apart.
- If V fails on Store A: nothing is changed anywhere for V; stop.
- If V succeeds on A and fails on B: stop immediately. A is at V, B at V−1. The run log (§3.5) and `--status` show this.
  Because every migration is backward compatible (expand/contract), both stores keep working on the current code.
- Next run: precheck sees different versions and **refuses a normal run**. Two recovery paths, chosen by the operator:
  1. **Repair forward** (usual): fix the cause on B (data violating a new constraint, a lock, a permission), then run
     `--repair`, which applies to the lagging store only the versions the other store already has (same checksums, same
     lock, backup still required), never anything newer.
  2. **Roll A back**: run A's guarded down script for V (`backend/migrations/down/`), which refuses if it would lose data
     (`docs/india-razorpay-design.md` §4.3); then both are at V−1.
- Restarting after a crash mid-run is safe: the crashed session's advisory lock and open transaction are released by
  PostgreSQL; committed versions are recorded; the next run resumes from precheck.

### 3.5 Logging and diagnostics (W5)
- Structured log line per store and version: `start`, `ok` (duration ms) or `failed` (error class, SQLSTATE, first line of the
  message), never connection strings or passwords (`Settings` already hides them).
- A local run log `.run/migrations/<timestamp>.json` (git-ignored) with the plan, results per store/version, and the
  backup used.
- `python -m app.migrate --status`: per store, applied versions with checksum, `applied_at`, `applied_by`; pending
  versions; checksum mismatches; current advisory-lock holder; result of the last run. Read-only.
- `python -m app.migrate --plan --backup …`: everything except applying (checksums, lint, precheck, lock acquisition and
  release, pending list). Read-only.

## 4. Implementation steps (each its own reviewed change, with tests first)
1. Pure functions + unit tests: `file_checksum`, `lint_migration`, `plan(applied_by_store, files)` (refuse divergent,
   mismatched, missing, NULL checksums; compute lockstep order).
2. Lock module with an injectable connection: try-lock loop with timeout and holder diagnostics.
3. Precheck integration: reuse `scripts/dbsafety.py` (`verify`, `precheck`) through an importable module.
4. Lockstep apply loop with per-migration `SET LOCAL` timeouts, checksum insert in the same transaction, run log.
5. CLI: `--status`, `--plan`, `--backup`, `--repair`, `--lock-timeout`, `--max-backup-age`; keep `migrate_database(url)`
   working for `tests/conftest.py` (test databases), with checksums recorded there too.
6. Checksum adoption command (§6).
7. Update `docs/database-safety.md` procedure to use `--plan` then the real run.

## 5. Tests (all against `*_test` databases or fakes; details in `docs/testing-plan.md`)
Checksum mismatch refused; missing file refused; NULL checksum refused until adopted; linted transaction control refused;
two runners started together (one waits/times out, no partial work); lock timeout message names the holder; failed precheck
refuses with no change; A succeeds / B fails leaves exactly one version of difference; normal run refused while divergent;
`--repair` applies only the missing version to B; crash simulation (process killed between A and B) then rerun;
`SET LOCAL lock_timeout` aborts cleanly while another session holds a table lock; `--status` and `--plan` write nothing.

## 6. Rollout (needs approval when implemented)
1. The new runner's bookkeeping change (`ALTER TABLE schema_migrations ADD COLUMN checksum TEXT, ADD COLUMN applied_by TEXT`)
   is applied like a migration: precheck, backup, test databases first.
2. **Adopt checksums** for 0001–0003 with an explicit command that records the hash only if the file on disk is byte-identical
   to its committed version (`git show 5115d9b:backend/migrations/<file>`; 0001 also exists at `e14e9d5`). Any difference →
   refuse and investigate.
3. From then on every migration (0004+) is applied only through `--plan` → approved real run.

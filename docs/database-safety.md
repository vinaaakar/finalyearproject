# Database safety: backups, restore checks, migrations and rollback

All tooling is local. Nothing is uploaded, and no tool starts, stops or recreates the Postgres container.
(`scripts/backup_to_drive.sh` is a separate, manual, *external* upload to Google Drive; it is not part of this procedure.)

## Tools

| Command | What it does | Writes to |
|---|---|---|
| `scripts/backup_db.sh` | `pg_dump -Fc` of `store_a` and `store_b`, SHA-256 per dump, readable-TOC check, per-table row counts taken before and after the dump and compared with the rows inside the dump, `MANIFEST.json` | `backups/db-<timestamp>/` (git-ignored, mode 700/600) |
| `scripts/dbsafety.py verify <dir>` | Re-checks checksums, TOC and dump row counts against the manifest | nothing |
| `scripts/dbsafety.py restore-check <dir> --confirm` | Verifies the backup, restores each dump into a **new scratch database** `<db>_restorecheck_<timestamp>`, compares row counts, then drops the scratch database (also on failure) | creates/drops scratch databases only |
| `scripts/dbsafety.py precheck` | Read-only: container healthy, both stores reachable, both at the same applied versions, no unknown versions, pending list, latest backup verified and less than 24 h old | nothing |

Safety rules enforced in code (and tested with a fake Docker in `scripts/tests/test_dbsafety.py`):
- Only `store_a`, `store_b` (or their `_test` copies) can be backed up.
- Only names matching `store_[ab](_test)?_restorecheck_YYYYMMDD_HHMMSS` can ever be created or dropped; the originals are never a
  restore target. An unverified (checksum-mismatched) backup is never restored.
- A backup taken while data was changing fails (row counts differ) instead of producing a silently inconsistent copy.
- Backups can only be read from or written under `backups/`.

**What the restore-check does NOT verify.** It restores with `--no-owner --no-privileges` into a scratch database and
compares **row counts only**. It does not check table/schema/sequence ownership, sequence positions, foreign-key validity
or migration compatibility. Passing it proves the dump is restorable and complete by count; it is **not** a rehearsal
of the full recovery procedure below.

**Performed on the real dev backup (2026-11-09, 14:22 IST, approved):**
`scripts/dbsafety.py restore-check backups/db-20261109-135303 --confirm` → exit code 0. Checksums verified first;
`store_a` and `store_b` were restored into `store_a_restorecheck_20261109_142246` and `store_b_restorecheck_20261109_142246`;
13 tables each, every row count matched the manifest; both scratch databases were dropped (0 remain); `store_a`, `store_b`,
`store_a_test`, `store_b_test`, the Postgres container and all services were unchanged. As stated above, this verified
row counts only. Each further run creates and drops scratch databases on the live instance and needs approval.

## Migration procedure (two stores)

1. `scripts/dbsafety.py precheck` must report *Ready*. Fix every listed problem first; never migrate one store when the
   two are already at different versions.
2. `scripts/backup_db.sh`, then `scripts/dbsafety.py restore-check backups/db-<ts> --confirm`.
3. Apply to the test databases first (`scripts/test.sh` migrates `store_*_test`), run the full suite.
4. Apply to a scratch copy restored from step 2 and run read-only checks against it.
5. Apply to the dev databases with the hardened runner (`backend/app/migrate.py`, Phase G):
   * once only, for databases migrated before checksums existed: `cd backend && .venv/bin/python -m app.migrate --adopt`
     (records each applied file's checksum only if it is byte-identical to its committed version);
   * `.venv/bin/python -m app.migrate --plan --backup backups/db-<ts>` — every check, nothing written;
   * `.venv/bin/python -m app.migrate --apply --backup backups/db-<ts>` — lockstep across both stores, checksums,
     advisory lock, enforced precheck, per-migration lock/statement timeouts, run log in `.run/migrations/`.
   `--status` is read-only at any time. The API refuses to start while any migration is pending (clear message).
6. `--status` / `precheck` again: both stores must be at the same version with matching checksums.

### If one store migrates and the other fails

The runner applies each version to Store A, then Store B, before the next version (lockstep). A failure in Store B
leaves Store B one version behind (its transaction rolls back) while Store A has that version; the next normal run
refuses with “stores are at different versions”.
- Do **not** retry blindly. Read the error; fix the cause (data that violates a new constraint, a lock, permissions).
- The application must be compatible with both versions for that period: every migration must be **additive and
  backward compatible** (expand/contract): new columns nullable or defaulted, constraints added only after code writes them.
- Then run `python -m app.migrate --repair --backup backups/db-<ts>`, which applies to the lagging store only the versions
  the other store already has (same checksums; never anything newer), or roll Store A back with its down script (below).

## Down scripts and rollback

- Location: `backend/migrations/down/<version>.down.sql`. The runner reads only `backend/migrations/*.sql`, so down scripts
  are never applied automatically (tested).
- Each down script reverses its migration and deletes its `schema_migrations` row, inside one transaction, and states its
  data impact in its header.
- `0003_policy_translations.down.sql` exists (drops translation columns; refillable from code; no customer data).
- **No down scripts for 0001/0002**: reversing them would delete customers, carts, orders and payments. Recovery from those is
  a restore, not a down script.
- Rules for new migrations (0004+): ship the down script in the same change; data-changing migrations copy previous values into
  a `<table>_backup_<version>` table so the down script can restore them exactly.

### Rollback order
1. Switch feature flags back (e.g. per-store market flag), so the old code path is used.
2. Run the down script, per store, after taking a fresh backup. Test it first on a scratch restore.
3. If data is inconsistent: follow **Recovery** below — restore into a **replacement** database with ownership preserved,
   validate it, and only then cut the application over. Never restore over the live database.

## Recovery: restoring a store into a replacement database

Every live table and sequence is **owned by the store role** (`store_a_app` / `store_b_app`; the database owner, see
`db/init/01-create-store-databases.sh`), and the dumps contain those `OWNER TO` statements. The migration runner connects
as the store role, and `ALTER TABLE` requires ownership — grants are not enough. Therefore a recovery must **preserve
ownership**: do **not** use `--no-owner` (that is only acceptable for the throw-away restore-check).

This procedure has two separate stages. **Stage 1 (restoration)** builds and validates a new database while the
application keeps using the current one. **Stage 2 (cutover)** switches the application; it changes credentials-bearing
configuration and restarts the API, so it needs explicit approval. Commands are shown for Store A; replace `a`/`store_a`
for Store B.

**Execution record.** Stage 1 (steps 0–4, then the cleanup now documented as step 7 — name confirmation followed by the
step 6 `DROP DATABASE` command) was rehearsed once, with approval, on
2026-11-09 (Phase 1.2C) from `backups/db-20261109-135303` into `store_a_recovered_20261109_165252` and
`store_b_recovered_20261109_165252`. All verification checks in step 4 passed for both stores (database, schema, table,
sequence and index ownership by the store role; connect permissions; sequence positions equal to the dump; no ID
collisions; 9 validated foreign keys with 0 orphan rows; all 13 row counts equal to the manifest; migrations 0001–0003),
and both databases were then dropped (0 remain); the original databases, container and services were unchanged.
Step 5 was **not** performed (it starts an additional API process, which was outside that approval), so application-level
recovery has not been rehearsed. A first attempt at step 3 failed on a shell quoting error; PostgreSQL rejected it before
execution, nothing changed, and the correct commands were then run. **Stage 2 has never been executed.**

### Stage 1 — restoration (no application impact)

0. Choose the backup: `scripts/dbsafety.py verify backups/db-<ts>` must pass. Choose a new name, e.g.
   `store_a_recovered_<YYYYMMDD_HHMMSS>` (never `store_a`).
1. Create the replacement database **owned by the store role**:
   ```sql
   -- docker exec -it avc_postgres psql -U postgres
   CREATE DATABASE store_a_recovered_<ts> OWNER store_a_app;
   ```
   Non-interactive form (same statement; use it when no terminal is attached, e.g. from a script). `ON_ERROR_STOP=1`
   makes any error fail the command instead of continuing:
   ```bash
   docker exec avc_postgres psql -U postgres -v ON_ERROR_STOP=1 \
     -c "CREATE DATABASE store_a_recovered_<ts> OWNER store_a_app;"
   ```
   Run one database per command with the name written out in full (avoid shell loops that build names from variables);
   step 3 can be run the same way, with one `-c` per statement.
2. Restore as the superuser **without `--no-owner`**, so the dump's `OWNER TO store_a_app` statements are applied, in one
   transaction so a failure leaves an empty database rather than a partial one:
   ```bash
   docker exec -i avc_postgres pg_restore -U postgres -d store_a_recovered_<ts> --exit-on-error --single-transaction \
     < backups/db-<ts>/store_a.dump
   ```
3. Re-apply connection permissions (as in `db/init`):
   ```sql
   REVOKE CONNECT ON DATABASE store_a_recovered_<ts> FROM PUBLIC;
   GRANT  CONNECT ON DATABASE store_a_recovered_<ts> TO store_a_app;
   ```
   Also confirm the other store's role cannot connect (it must not have been granted anything).
4. Verify, connected to the new database (`psql -U postgres -d store_a_recovered_<ts>`); every check must pass:
   | Check | Query | Expected |
   |---|---|---|
   | Table ownership | `SELECT tablename, tableowner FROM pg_tables WHERE schemaname = 'public' AND tableowner <> 'store_a_app';` | 0 rows |
   | Schema ownership | `SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'public';` | `pg_database_owner` (PostgreSQL 15 default, i.e. the database owner `store_a_app`) or `store_a_app` |
   | Sequence ownership | `SELECT sequencename, sequenceowner FROM pg_sequences WHERE schemaname = 'public' AND sequenceowner <> 'store_a_app';` | 0 rows |
   | Sequence positions | `SELECT sequencename, last_value FROM pg_sequences WHERE schemaname = 'public';` compared with the `setval(...)` lines in `pg_restore -f - backups/db-<ts>/store_a.dump` | identical; and `order_number_seq.last_value` ≥ the highest numeric part of `orders.order_number` created by checkout |
   | Foreign keys | `SELECT conname FROM pg_constraint WHERE contype = 'f' AND NOT convalidated;` and orphan spot-checks, e.g. `SELECT count(*) FROM order_items i LEFT JOIN orders o ON o.id = i.order_id WHERE o.id IS NULL;` | 0 rows / 0 |
   | Row counts | per-table `count(*)` compared with `tables` in `MANIFEST.json` (the same comparison `dbsafety.py` makes) | identical |
   | Migration compatibility | `SELECT version FROM schema_migrations ORDER BY 1;` | equals the versions in `backend/migrations/*.sql` that the running code expects, and equals the other store's versions |
   | Role can work | connect **as `store_a_app`** and run `SELECT count(*) FROM orders;` | succeeds |
5. Validate behaviour **before any traffic**: start a **separate, temporary** API process on a spare port (never the live
   API) with `STORE_A_DATABASE_URL` pointing at the replacement database, and run read-only checks: `/api/health`, catalogue,
   a known customer's order lookup through the test client, cart read. Compare key business facts (order numbers, statuses,
   totals, payment records) with the backup manifest and with what the store owner expects. Stop the temporary process.
6. If any check fails: keep the current database in use, drop only the replacement database
   (`DROP DATABASE store_a_recovered_<ts>;`, after confirming the name), investigate, and repeat from step 0.
7. **Rehearsal only — cleanup after a successful verification.** In a real recovery the validated replacement database is
   kept and goes on to Stage 2. In a rehearsal it is removed once every check has passed:
   1. Confirm the exact name: it must match `store_[ab]_recovered_<YYYYMMDD_HHMMSS>` for this rehearsal, must not be
      `store_a`, `store_b`, `store_a_test` or `store_b_test`, and must exist:
      `docker exec avc_postgres psql -U postgres -At -c "SELECT count(*) FROM pg_database WHERE datname = 'store_a_recovered_<ts>';"` → `1`.
   2. Drop that one database (repeat separately for Store B):
      `docker exec avc_postgres psql -U postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE store_a_recovered_<ts>;"`
   3. Confirm nothing is left and the originals are as before:
      `docker exec avc_postgres psql -U postgres -At -c "SELECT count(*) FROM pg_database WHERE datname LIKE '%\_recovered\_%';"` → `0`,
      and compare the database list, owners and access lists with the values recorded before step 1.
   If a drop fails, stop and report the remaining name and error; do not retry with different commands.

### Stage 2 — application cutover (needs explicit approval)

1. Announce a short write freeze. Take a final backup of the current database (`scripts/backup_db.sh`) even if it is
   believed corrupt — it is evidence and a fallback.
2. Point the store at the replacement database: change `STORE_A_DATABASE_URL` in `.env` (credential-bearing configuration:
   approval required). Do not rename or drop the old database.
3. Restart the API only: `./scripts/restart_api.sh` (never `docker compose`). Postgres and the storefronts keep running.
4. Verify: `/api/health` shows both stores reachable; `scripts/dbsafety.py precheck`; storefront pages load; a read-only
   order lookup works.
5. Cutover rollback: restore the previous `STORE_A_DATABASE_URL` and restart the API again. The old database was never
   modified, so this is immediate.
6. After a stable period (agreed with the store owner), archive the old database with a backup before any decision to drop
   it; dropping a database is a separate approval.

-- DOWN for 0003_policy_translations. NEVER applied automatically: app/migrate.py only reads backend/migrations/*.sql
-- (top level). Run manually, per store, only after `scripts/backup_db.sh` + `scripts/dbsafety.py restore-check`,
-- first on a *_test or scratch database. See docs/database-safety.md.
-- Effect: removes the Tamil/Hindi policy translations (they can be refilled from app/policy_translations.py by
-- `python -m app.seed`, which only fills empty translations). No customer, order or payment data is affected.
BEGIN;
ALTER TABLE policies
    DROP COLUMN IF EXISTS summary_ta,
    DROP COLUMN IF EXISTS details_ta,
    DROP COLUMN IF EXISTS summary_hi,
    DROP COLUMN IF EXISTS details_hi;
DELETE FROM schema_migrations WHERE version = '0003_policy_translations';
COMMIT;

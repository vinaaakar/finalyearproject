-- DOWN for 0004_policy_truth. NEVER applied automatically: app/migrate.py only reads backend/migrations/*.sql
-- (top level). Run manually, per store, only after `scripts/backup_db.sh` + `scripts/dbsafety.py restore-check`,
-- first on a *_test or scratch database. See docs/database-safety.md.
-- Effect: puts back the policy text saved by 0004 (re-introducing the unsupported claims). Refuses if the backup
-- table is missing. No customer, order or payment data is affected.
BEGIN;
DO $$ BEGIN
  IF to_regclass('public.policies_backup_0004') IS NULL THEN RAISE EXCEPTION 'refusing: policies_backup_0004 is missing'; END IF;
END $$;
UPDATE policies p SET summary = b.summary, details = b.details, summary_ta = b.summary_ta, details_ta = b.details_ta,
                      summary_hi = b.summary_hi, details_hi = b.details_hi
FROM policies_backup_0004 b WHERE b.topic = p.topic;
DROP TABLE policies_backup_0004;
DELETE FROM schema_migrations WHERE version = '0004_policy_truth';
COMMIT;

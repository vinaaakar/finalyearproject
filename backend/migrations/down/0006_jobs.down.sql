-- DOWN for 0006_jobs. NEVER applied automatically. Run manually, per store, after `scripts/backup_db.sh` +
-- `scripts/dbsafety.py restore-check`, first on a *_test or scratch database (docs/database-safety.md).
-- Refuses while undelivered outbox work exists (it would be lost) unless SET avc.allow_data_loss = 'on'.
-- Requires the code from before Phase G (current fulfilment code writes to outbox).
BEGIN;
DO $$ BEGIN
  IF coalesce(current_setting('avc.allow_data_loss', true), 'off') <> 'on' AND EXISTS (SELECT 1 FROM outbox WHERE status = 'pending') THEN
    RAISE EXCEPTION 'refusing: pending outbox work exists; back up, then SET avc.allow_data_loss = ''on'' to proceed';
  END IF;
END $$;
DROP TABLE outbox;
DROP TABLE job_runs;
DELETE FROM schema_migrations WHERE version = '0006_jobs';
COMMIT;

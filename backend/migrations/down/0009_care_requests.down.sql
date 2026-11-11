-- DOWN for 0009_care_requests. NEVER applied automatically. Run manually, per store, after `scripts/backup_db.sh` +
-- `scripts/dbsafety.py restore-check`, first on a *_test or scratch database (docs/database-safety.md).
-- Refuses while any care request exists (customer complaints, returns, refund requests and their history would be lost)
-- unless SET avc.allow_data_loss = 'on'.
BEGIN;
DO $$ BEGIN
  IF coalesce(current_setting('avc.allow_data_loss', true), 'off') <> 'on' AND EXISTS (SELECT 1 FROM care_requests) THEN
    RAISE EXCEPTION 'refusing: care requests exist; back up, then SET avc.allow_data_loss = ''on''';
  END IF;
END $$;
DROP TABLE care_request_events;
DROP TABLE care_requests;
DROP SEQUENCE care_request_seq;
DELETE FROM schema_migrations WHERE version = '0009_care_requests';
COMMIT;

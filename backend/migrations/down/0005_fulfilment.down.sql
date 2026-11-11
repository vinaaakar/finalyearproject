-- DOWN for 0005_fulfilment. NEVER applied automatically: app/migrate.py only reads backend/migrations/*.sql
-- (top level). Run manually, per store, only after `scripts/backup_db.sh` + `scripts/dbsafety.py restore-check`,
-- first on a *_test or scratch database. See docs/database-safety.md.
-- Effect: removes the status history table and the tracking_url / shipped_at / delivered_at columns.
-- Refuses if any history row or tracking data exists (it would be lost), unless the session sets
--   SET avc.allow_data_loss = 'on';
-- after a verified backup. Order statuses, carriers and tracking numbers on orders are kept either way.
BEGIN;
DO $$ BEGIN
  IF coalesce(current_setting('avc.allow_data_loss', true), 'off') <> 'on' AND (
       EXISTS (SELECT 1 FROM order_status_history)
       OR EXISTS (SELECT 1 FROM orders WHERE tracking_url IS NOT NULL OR shipped_at IS NOT NULL OR delivered_at IS NOT NULL)) THEN
    RAISE EXCEPTION 'refusing: order history / tracking data exists; back up, then SET avc.allow_data_loss = ''on'' to proceed';
  END IF;
END $$;
DROP TABLE order_status_history;
ALTER TABLE orders DROP COLUMN tracking_url, DROP COLUMN shipped_at, DROP COLUMN delivered_at;
DELETE FROM schema_migrations WHERE version = '0005_fulfilment';
COMMIT;

-- DOWN for 0007_order_contact_phone. NEVER applied automatically. Run manually, per store, after `scripts/backup_db.sh`
-- + `scripts/dbsafety.py restore-check`, first on a *_test or scratch database (docs/database-safety.md).
-- Refuses while any order has a phone number (it would be lost) unless SET avc.allow_data_loss = 'on'.
BEGIN;
DO $$ BEGIN
  IF coalesce(current_setting('avc.allow_data_loss', true), 'off') <> 'on' AND EXISTS (SELECT 1 FROM orders WHERE shipping_phone IS NOT NULL) THEN
    RAISE EXCEPTION 'refusing: orders have phone numbers; back up, then SET avc.allow_data_loss = ''on'' to proceed';
  END IF;
END $$;
ALTER TABLE orders DROP COLUMN shipping_phone;
DELETE FROM schema_migrations WHERE version = '0007_order_contact_phone';
COMMIT;

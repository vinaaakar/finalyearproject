-- DOWN for 0008_price_lists. NEVER applied automatically. Run manually, per store, after `scripts/backup_db.sh` +
-- `scripts/dbsafety.py restore-check`, first on a *_test or scratch database (docs/database-safety.md).
-- Refuses while approved prices or non-USD orders exist (they would be lost / become ambiguous) unless
-- SET avc.allow_data_loss = 'on'.
BEGIN;
DO $$ BEGIN
  IF coalesce(current_setting('avc.allow_data_loss', true), 'off') <> 'on'
     AND (EXISTS (SELECT 1 FROM product_prices) OR EXISTS (SELECT 1 FROM orders WHERE currency <> 'USD')) THEN
    RAISE EXCEPTION 'refusing: approved prices or non-USD orders exist; back up, then SET avc.allow_data_loss = ''on''';
  END IF;
END $$;
ALTER TABLE orders DROP COLUMN currency;
DROP TABLE product_prices;
DELETE FROM schema_migrations WHERE version = '0008_price_lists';
COMMIT;

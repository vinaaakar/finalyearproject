-- DOWN for 0010_saved_addresses. NEVER applied automatically.
-- Refuses while any saved address exists unless SET avc.allow_data_loss = 'on'.
BEGIN;
DO $$ BEGIN
  IF coalesce(current_setting('avc.allow_data_loss', true), 'off') <> 'on' AND EXISTS (SELECT 1 FROM customer_addresses) THEN
    RAISE EXCEPTION 'refusing: saved addresses exist; back up, then SET avc.allow_data_loss = ''on''';
  END IF;
END $$;
DROP TABLE customer_addresses;
DELETE FROM schema_migrations WHERE version = '0010_saved_addresses';
COMMIT;

-- Country-aware checkout: the recipient's phone number (required for India deliveries, optional for the US), stored in
-- E.164 form (+919876543210, +13035550100). Additive only: existing rows keep NULL; older code ignores the column.
-- Down: down/0007_order_contact_phone.down.sql.
ALTER TABLE orders
    ADD COLUMN shipping_phone TEXT CHECK (shipping_phone IS NULL OR shipping_phone ~ '^\+[1-9][0-9]{7,14}$');

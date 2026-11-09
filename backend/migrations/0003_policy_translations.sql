-- Tamil and Hindi versions of each policy, so the assistant can answer policy questions in the
-- customer's language from store data (not machine translation at request time).
ALTER TABLE policies
    ADD COLUMN summary_ta TEXT,
    ADD COLUMN details_ta TEXT,
    ADD COLUMN summary_hi TEXT,
    ADD COLUMN details_hi TEXT;

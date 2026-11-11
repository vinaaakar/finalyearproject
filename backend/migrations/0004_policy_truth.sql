-- Phase A (content truth): remove policy claims this system cannot honour from the STORED text.
-- Until now these were only filtered at read time (app/assistant/truth.py); the stored rows still said them.
--   * Store A returns: "Return shipping is free with the prepaid label from your account." — no such label exists.
--   * Store B returns: "… for a refund or store credit" — there is no store credit.
--   * Payment (both stores): card / PayPal / Apple Pay / Google Pay / gift-card claims — only a sandbox exists.
--     Replaced by the same sandbox statement the API and assistant already give (truth.PAYMENT_CAPABILITY).
-- Guarded and data-preserving: every original row is copied to policies_backup_0004 first; replacements are literal
-- (replace()) on the exact seeded sentences, so edited/owner-written text is left alone; no row is deleted.
-- Business rules (return windows, fees, warranty periods) are NOT changed: they need owner confirmation
-- (docs/business-information.md). Down: down/0004_policy_truth.down.sql restores the backup.

CREATE TABLE policies_backup_0004 AS SELECT p.*, now() AS saved_at FROM policies p;

UPDATE policies SET
    details    = replace(details,    ' Return shipping is free with the prepaid label from your account.', ''),
    details_ta = replace(details_ta, ' உங்கள் கணக்கில் உள்ள முன்கட்டண லேபிளுடன் திருப்பி அனுப்புவது இலவசம்.', ''),
    details_hi = replace(details_hi, ' आपके अकाउंट के प्रीपेड लेबल से वापसी शिपिंग मुफ़्त है।', '')
WHERE topic = 'returns';

UPDATE policies SET
    details    = replace(details,    'for a refund or store credit', 'for a refund'),
    details_ta = replace(details_ta, 'பணம் அல்லது ஸ்டோர் கிரெடிட் பெறலாம்', 'பணம் பெறலாம்'),
    details_hi = replace(details_hi, 'रिफ़ंड या स्टोर क्रेडिट लिया जा सकता है', 'रिफ़ंड लिया जा सकता है')
WHERE topic = 'returns';

UPDATE policies SET
    summary = 'Right now this store only takes test-mode (sandbox) payments: no real money moves. Cards, UPI, wallets, gift cards and cash on delivery are not accepted yet.', details = 'Right now this store only takes test-mode (sandbox) payments: no real money moves. Cards, UPI, wallets, gift cards and cash on delivery are not accepted yet.',
    summary_ta = 'இப்போது இந்த ஸ்டோரில் சோதனை (sandbox) பணம் செலுத்துதல் மட்டுமே உள்ளது: உண்மையான பணம் எதுவும் நகராது. கார்டுகள், UPI, வாலெட்டுகள், கிஃப்ட் கார்டுகள் அல்லது கேஷ் ஆன் டெலிவரி இன்னும் ஏற்றுக்கொள்ளப்படுவதில்லை.', details_ta = 'இப்போது இந்த ஸ்டோரில் சோதனை (sandbox) பணம் செலுத்துதல் மட்டுமே உள்ளது: உண்மையான பணம் எதுவும் நகராது. கார்டுகள், UPI, வாலெட்டுகள், கிஃப்ட் கார்டுகள் அல்லது கேஷ் ஆன் டெலிவரி இன்னும் ஏற்றுக்கொள்ளப்படுவதில்லை.',
    summary_hi = 'अभी यह स्टोर सिर्फ़ टेस्ट-मोड (sandbox) भुगतान लेता है: कोई असली पैसा नहीं कटता। कार्ड, UPI, वॉलेट, गिफ़्ट कार्ड और कैश ऑन डिलीवरी अभी स्वीकार नहीं किए जाते।', details_hi = 'अभी यह स्टोर सिर्फ़ टेस्ट-मोड (sandbox) भुगतान लेता है: कोई असली पैसा नहीं कटता। कार्ड, UPI, वॉलेट, गिफ़्ट कार्ड और कैश ऑन डिलीवरी अभी स्वीकार नहीं किए जाते।'
WHERE topic = 'payment'
  AND (summary || ' ' || details) ~* '(visa|mastercard|american express|discover|paypal|apple pay|google pay|gift card)';

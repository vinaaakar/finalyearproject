"""Phase A: customer-facing store information contains only what the system can honour, and the stored policy
text has been corrected by migration 0004 (guarded, with a backup)."""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from app.assistant import truth
from app.seed import SEED
from app.policy_translations import POLICY_TRANSLATIONS
from app.stores import StoreId

CLAIMS = ("visa", "mastercard", "paypal", "apple pay", "google pay", "gift card", "prepaid", "store credit",
          "கிஃப்ட்", "முன்கட்டண", "ஸ்டோர் கிரெடிட்", "गिफ़्ट", "प्रीपेड", "स्टोर क्रेडिट")
MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "0004_policy_truth.sql"
DOWN = Path(__file__).resolve().parents[1] / "migrations" / "down" / "0004_policy_truth.down.sql"


def _no_claims(text: str) -> bool:
    low = text.lower()
    return not any(c in low for c in CLAIMS)


@pytest.mark.parametrize("store", [s.value for s in StoreId])
@pytest.mark.parametrize("lang", ["en", "ta", "hi"])
def test_store_info_policies_are_verified(client, store, lang):
    r = client.get(f"/api/stores/{store}", params={"lang": lang})
    assert r.status_code == 200
    body = r.json()
    assert body["policy_language"] == lang
    for topic, p in body["policies"].items():
        if topic == "payment":
            continue   # checked exactly below: it names the methods it does NOT accept
        assert _no_claims(p["summary"] + " " + p["details"]), (store, lang, topic, p)
    assert body["policies"]["payment"]["details"] == truth.PAYMENT_CAPABILITY["sandbox"][lang]


def test_store_info_rejects_unknown_language(client):
    assert client.get("/api/stores/store-a", params={"lang": "fr"}).status_code == 422


def test_seed_and_translations_have_no_unsupported_claims():
    for store, data in SEED.items():
        raw = {t: {"summary": s, "details": d} for t, s, d in data["policies"]}
        assert truth.policy_content_warnings(raw) == [], store
        for topic, langs in POLICY_TRANSLATIONS[store].items():
            for lang, (s, d) in langs.items():
                if topic == "payment":
                    assert s == d == truth.PAYMENT_CAPABILITY["sandbox"][lang]
                    continue
                assert _no_claims(s + " " + d), (store, topic, lang)


def test_business_rules_are_kept():
    """Correcting claims must not change the store's business rules (owner decisions)."""
    a = {t: d for t, _, d in SEED[StoreId.STORE_A]["policies"]}
    b = {t: d for t, _, d in SEED[StoreId.STORE_B]["policies"]}
    assert "60 days" in a["returns"] and "2 years" in a["warranty"] and "$75" in a["shipping"]
    assert "30 days" in b["returns"] and "1 year" in b["warranty"] and "$4.99" in b["shipping"]


OLD = {
    "returns_a": ("Return unused items in original packaging within 60 days of delivery for a full refund to the original payment "
                  "method. Used gear with a manufacturing defect is covered by warranty instead. Return shipping is free with the "
                  "prepaid label from your account."),
    "returns_b": ("Unused kitchenware can be returned within 30 days for a refund or store credit. Opened coffee, tea and other "
                  "food items are final sale unless they arrived damaged. Damaged items are replaced free of charge."),
    "payment": "Visa, Mastercard, American Express, Discover, PayPal and Summit gift cards are accepted.",
}


def test_migration_0004_corrects_old_text_and_keeps_a_backup(settings):
    """Run the migration body against a throwaway schema holding the OLD seeded text (never the dev databases)."""
    url = settings.store_database_urls["store-a"]
    assert url.rstrip("/").endswith("_test")
    with psycopg.connect(url, autocommit=False) as conn:
        try:
            conn.execute("CREATE SCHEMA phase_a_check")
            conn.execute("SET search_path TO phase_a_check")
            conn.execute("CREATE TABLE policies (topic TEXT PRIMARY KEY, summary TEXT, details TEXT, summary_ta TEXT, details_ta TEXT, "
                         "summary_hi TEXT, details_hi TEXT)")
            conn.execute("INSERT INTO policies VALUES ('returns', 's', %s, 's', NULL, 's', NULL), ('payment', 'We accept major cards.', %s, 'x', 'x', 'x', 'x'), "
                         "('warranty', 'w', 'Owner-written text mentioning nothing unsupported.', NULL, NULL, NULL, NULL)",
                         [OLD["returns_a"], OLD["payment"]])
            conn.execute(MIGRATION.read_text())
            rows = {r[0]: r for r in conn.execute("SELECT topic, summary, details, details_ta FROM policies").fetchall()}
            assert rows["returns"][2] == OLD["returns_a"].replace(" Return shipping is free with the prepaid label from your account.", "")
            assert "60 days" in rows["returns"][2]
            assert rows["payment"][2] == truth.PAYMENT_CAPABILITY["sandbox"]["en"]
            assert rows["payment"][3] == truth.PAYMENT_CAPABILITY["sandbox"]["ta"]
            assert rows["warranty"][2] == "Owner-written text mentioning nothing unsupported."   # untouched
            backup = {r[0]: r[1] for r in conn.execute("SELECT topic, details FROM policies_backup_0004").fetchall()}
            assert backup["returns"] == OLD["returns_a"] and backup["payment"] == OLD["payment"]
            # store B wording
            conn.execute("UPDATE policies SET details = %s WHERE topic = 'returns'", [OLD["returns_b"]])
            conn.execute("DROP TABLE policies_backup_0004")
            conn.execute(MIGRATION.read_text())
            d = conn.execute("SELECT details FROM policies WHERE topic = 'returns'").fetchone()[0]
            assert "store credit" not in d and "30 days for a refund." in d
        finally:
            conn.rollback()   # nothing persists


def test_down_script_is_guarded_and_restores():
    sql = DOWN.read_text()
    assert "refusing: policies_backup_0004 is missing" in sql
    assert "DELETE FROM schema_migrations WHERE version = '0004_policy_truth'" in sql
    assert "DELETE FROM policies" not in sql


# ---- business identity questions: answered with what is published, never invented ---------------------------------
import re as _re

_DIGITS = _re.compile(r"\d{6,}|\+\d|\b\d{2}[A-Z]{5}\d{4}")   # phone numbers, GSTIN-like strings


@pytest.mark.parametrize("store, email", [("store-a", "help@summittrail.example.com"), ("store-b", "care@bloomandbrew.example.com")])
@pytest.mark.parametrize("message, lang, marker", [
    ("What is your GST number?", "en", "hasn't published"),
    ("What's your phone number?", "en", "hasn't published"),
    ("Where is your store located? I want your address", "en", "hasn't published"),
    ("உங்கள் கடை முகவரி என்ன?", "ta", "வெளியிடவில்லை"),
    ("आपका जीएसटी नंबर क्या है?", "hi", "प्रकाशित नहीं"),
])
def test_business_identity_is_never_invented(client, store, email, message, lang, marker):
    r = client.post(f"/api/stores/{store}/chat", json={"message": message, "history": [], "channel": "web_chat",
                                                         "conversation_language": lang})
    assert r.status_code == 200
    body = r.json()
    assert marker in body["reply"], body["reply"]
    assert email in body["reply"]
    assert not _DIGITS.search(body["reply"]), body["reply"]
    assert not body["requires_login"]
    assert body["products"] == []


def test_invoice_requests_still_go_to_invoice_handling(client):
    r = client.post("/api/stores/store-a/chat", json={"message": "Can I get a GST invoice for my order?", "history": [],
                                                      "channel": "web_chat", "conversation_language": "en"}).json()
    assert "hasn't published" not in r["reply"]
    assert r["requires_login"] or "invoice" in r["reply"].lower()

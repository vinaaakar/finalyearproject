"""Phase 1 — trust, correctness and customer protection.

One section per audit finding (C1, C2, H1, H2, H3, H5, cancellation, ticket intent), each in Tamil, English and
Hindi where the answer is customer-facing. Runs against the *_test databases with synthetic accounts and orders;
the language model is either off or a scripted fake. Nothing here touches the development databases.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections import defaultdict

import pytest

from app.assistant import i18n, truth
from app.assistant.intent import detect_intent, parse_budget
from app.assistant.service import STATUS_LABELS, Assistant, ChatResult, format_amount
from app.phone import session as phone_session
from app.stores import StoreId
from tests.conftest import ALEX, JORDAN, MARIA, PW_A, PW_B, login, make_client
from tests.test_assistant import FakeLLM
from tests.test_assistant_security import ScriptedLLM
from tests.test_customer_care import DEVANAGARI, EMAIL_A, EMAIL_B, TAMIL, ask, place_order

# Claims of accepted brands (the honest answer may still NAME categories it doesn't accept, e.g. "gift cards … not accepted").
PAYMENT_BRANDS = re.compile(r"visa|mastercard|american express|amex|discover|paypal|apple pay|google pay|summit gift|bloom & brew gift|"
                            r"major cards|முக்கிய கார்டுகள்|प्रमुख कार्ड", re.I)
REFUND_DONE = re.compile(r"\brefunded\b|பணம் திருப்பித் தரப்பட்டது|रिफ़ंड हो गया|रिफंड हो गया|रिफ़ंड हुआ")


# =========================================================================================================
# C1 — a returned order never implies a refund
# =========================================================================================================
def test_status_labels_never_claim_a_refund():
    assert STATUS_LABELS["returned"] == "returned"
    for lang in ("ta", "hi"):
        label = i18n.STATUS[lang]["returned"]
        assert not re.search(r"ரீஃபண்ட்|பணம் திருப்பி|रिफ़ंड|रिफंड", label), label


def test_backend_cannot_establish_any_refund_state():
    # The schema has no refund records: only "item returned" (the order status) is knowable.
    assert {k for k, v in truth.REFUND_STATES.items() if v} == {"item_returned"}
    assert truth.refund_evidence({"status": "returned"}) == "none"


@pytest.mark.parametrize("lang, message, marker", [
    ("en", "Did my refund for BB-20004 come through?", "can't see a refund record"),
    ("ta", "BB-20004 ஆர்டருக்கு ரீஃபண்ட் வரவில்லை", "ரீஃபண்ட் பதிவு எதுவும் எனக்குத் தெரியவில்லை"),
    ("hi", "BB-20004 का रिफंड नहीं मिला", "कोई रिफ़ंड रिकॉर्ड नहीं दिखता"),
])
def test_returned_order_refund_answer_is_conservative_in_every_language(client, lang, message, marker):
    maria = login(client, "store-b", MARIA, PW_B)
    body = ask(client, "store-b", message, maria)
    assert body["language"] == lang
    assert "BB-20004" in body["reply"] and marker in body["reply"], body["reply"]
    assert EMAIL_B in body["reply"]
    assert not REFUND_DONE.search(body["reply"]), body["reply"]
    for o in body["orders"]:
        assert not REFUND_DONE.search(o["status_label"])


def test_order_history_api_labels_returned_orders_honestly(client):
    maria = login(client, "store-b", MARIA, PW_B)
    orders = client.get("/api/stores/store-b/orders", headers=maria).json()["orders"]
    returned = [o for o in orders if o["status"] == "returned"]
    assert returned and all(o["status_label"] == "returned" for o in returned)


def test_cancelled_after_payment_wording_promises_nothing():
    for lang in ("ta", "en", "hi"):
        text = i18n.t(lang, "pay_cancelled_paid", number="SA-50001", amount="$45.95", email=EMAIL_A)
        assert "SA-50001" in text and "$45.95" in text and EMAIL_A in text
        assert not REFUND_DONE.search(text)
    assert "can't see a refund recorded" in i18n.t("en", "pay_cancelled_paid", number="X", amount="$1.00", email=EMAIL_A)


# =========================================================================================================
# C2 — payment and return answers reflect what is actually implemented
# =========================================================================================================
@pytest.mark.parametrize("store", ["store-a", "store-b"])
@pytest.mark.parametrize("lang, message, test_word", [
    ("en", "What payment methods do you accept?", "test-mode"),
    ("ta", "என்ன பேமெண்ட் முறைகள் ஏற்றுக்கொள்கிறீர்கள்?", "சோதனை"),
    ("hi", "आप कौन से पेमेंट तरीके स्वीकार करते हैं?", "टेस्ट"),
])
def test_payment_answers_come_from_real_capabilities(client, store, lang, message, test_word):
    body = ask(client, store, message)
    assert body["language"] == lang
    assert test_word in body["reply"], body["reply"]
    assert not PAYMENT_BRANDS.search(body["reply"]), body["reply"]


def test_upi_and_cash_on_delivery_are_not_promised(client):
    body = ask(client, "store-a", "Can I pay with UPI or cash on delivery?")
    assert "not accepted yet" in body["reply"] and "UPI" in body["reply"]
    assert "shipping" not in body["intents"]


@pytest.mark.parametrize("store, window", [("store-a", "60 days"), ("store-b", "30 days")])
@pytest.mark.parametrize("lang, message", [
    ("en", "What is your return policy?"), ("ta", "திருப்பி அனுப்பும் கொள்கை என்ன?"), ("hi", "रिटर्न पॉलिसी क्या है?"),
])
def test_return_answers_drop_unsupported_services_but_keep_the_rules(client, store, window, lang, message):
    body = ask(client, store, message)
    reply = body["reply"]
    assert not re.search(r"prepaid|store credit|முன்கட்டண லேபிள|ஸ்டோர் கிரெடிட்|प्रीपेड लेबल|स्टोर क्रेडिट", reply, re.I), reply
    digits = window.split()[0]
    assert digits in reply, reply   # the real return window is still stated


def test_model_never_sees_unsupported_policy_claims(settings):
    fake = FakeLLM()
    with make_client(settings, llm=fake) as c:
        assert ask(c, "store-a", "What is your return policy?")["source"] == "llm"
    sent = json.dumps(fake.calls, ensure_ascii=False).lower()
    assert "prepaid" not in sent and "paypal" not in sent and "visa" not in sent


def test_stored_policy_problems_are_reported_not_hidden(client):
    # Phase A (migration 0004 + corrected seed) removed the stored claims, so a correctly seeded store reports none …
    warnings = client.get("/api/health").json()["policy_warnings"]
    assert warnings == {}   # stores without problems are omitted
    # … while the pre-0004 text is still detected (the detector itself is unchanged).
    old = {"payment": {"summary": "We accept major cards, PayPal and gift cards.", "details": "Visa and PayPal."},
           "returns": {"summary": "60 days.", "details": "Return shipping is free with the prepaid label from your account."}}
    assert truth.policy_content_warnings(old) == ["payment: card / wallet / gift-card payments", "returns: prepaid return label"]


def test_strip_unsupported_keeps_business_rules():
    text = "Returns within 60 days. Return shipping is free with the prepaid label from your account."
    assert truth.strip_unsupported("returns", text) == "Returns within 60 days."
    p = truth.verified_policies({"returns": {"summary": "Returns within 30 days.",
                                             "details": "Kitchenware within 30 days for a refund or store credit. Food is final sale."},
                                 "payment": {"summary": "We accept PayPal.", "details": "Visa and gift cards."}}, None, "en")
    assert "store credit" not in p["returns"]["details"] and "30 days" in p["returns"]["details"]
    assert "PayPal" not in p["payment"]["details"] and "isn't available" in p["payment"]["details"]


# =========================================================================================================
# H1 — product answers come only from the catalogue
# =========================================================================================================
HALLUCINATION = "For winter you need a -20°F four-season bag, insulated climbing boots and a parka from our Everest line."


@pytest.mark.parametrize("store, message", [
    ("store-a", "What gear do I need for winter camping in the mountains?"),
    ("store-a", "Do you have a 2-person tent?"),
    ("store-a", "How much is the headlamp?"),
    ("store-b", "Which tea has the least caffeine?"),
    ("store-b", "I like light, fruity coffee. What should I buy?"),
    ("store-b", "Is the House Blend in stock?"),
])
def test_product_questions_never_use_the_model(settings, store, message):
    fake = ScriptedLLM(HALLUCINATION)
    with make_client(settings, llm=fake) as c:
        body = ask(c, store, message)
    assert fake.calls == [] and body["source"] == "rules"
    assert "parka" not in body["reply"] and "Everest" not in body["reply"]


def test_winter_advice_lists_only_real_products_with_a_safety_note(client):
    body = ask(client, "store-a", "What gear do I need for winter camping in the mountains?")
    catalog = {p["slug"]: p for p in client.get("/api/stores/store-a/products").json()["products"]}
    assert all(p["slug"] in catalog for p in body["products"])
    assert "only go by the product descriptions" in body["reply"]


def test_out_of_stock_products_are_labelled_as_such(client):
    body = ask(client, "store-a", "Do you have a 4-person tent?")
    assert "Basecamp 4-Person Tent — $449.00, currently out of stock" in body["reply"]


def test_empty_search_is_reported_accurately(client):
    body = ask(client, "store-a", "Do you sell kayaks?")
    assert body["products"] == [] and "couldn't find a matching product" in body["reply"]


def test_legitimate_recommendation_uses_server_names_and_prices(client):
    body = ask(client, "store-b", "I like light, fruity coffee. What should I buy?")
    assert body["products"][0]["slug"] == "ethiopia-yirgacheffe-beans"
    assert "Ethiopia Yirgacheffe Whole Beans — $19.00" in body["reply"] and "jasmine" in body["reply"]


def test_caffeine_question_admits_the_catalogue_has_no_caffeine_data(client):
    body = ask(client, "store-b", "Which tea has the least caffeine?")
    assert "caffeine levels" in body["reply"] and "least caffeine" not in body["reply"].replace("Which tea has the least caffeine", "")


def test_each_assistant_keeps_its_own_voice(client):
    a = ask(client, "store-a", "Do you have a tent?")["reply"]
    b = ask(client, "store-b", "Do you have tea?")["reply"]
    assert a.startswith("From our trail gear") and b.startswith("From our coffee and tea shelf")
    assert ask(client, "store-a", "கூடாரம் இருக்கிறதா?")["reply"].startswith("எங்கள் மலையேற்றப் பொருட்களில்")
    assert ask(client, "store-b", "क्या चाय है?")["reply"].startswith("हमारी कॉफ़ी और चाय की शेल्फ़ से")


GROUND_CTX = {"store": {"name": "Summit Trail Co."},
              "policies": {"shipping": {"details": "Standard shipping is $6.95 under $75 and free over $75. Standard delivery takes 3–5 business days."}}}
GROUND_DRAFT = "Standard shipping is $6.95 under $75 and free over $75. Standard delivery takes 3–5 business days."
CATALOG = ["Ridgeline 2-Person Tent", "Basecamp 4-Person Tent", "Daytrip 22L Daypack"]


@pytest.mark.parametrize("reply, ok", [
    ("Standard shipping is $6.95, and it's free over $75. Delivery takes 3–5 business days.", True),
    ("Shipping is $5.95 for all orders.", False),                                         # fabricated price
    ("Shipping is free over ₹6000.", False),                                               # invented rupee amount
    ("Standard shipping takes 1 business day.", False),                                    # number not in the facts
    ("Standard shipping is $6.95. Pair it with our Ridgeline 2-Person Tent!", False),      # product not in the answer
    ("Standard shipping is $6.95. See https://summittrail.example.com/shipping", False),  # fabricated URL
    ("Standard shipping is $6.95. Click this link: [insert login link]", False),           # placeholder
    ("Standard shipping is $6.95. Please sign in to see your account details.", False),   # sign-in claim not in draft
    ("We recommend an insulated parka, crampons and a four-season expedition bivouac.", False),  # invented gear
    ("Ask Maple at Bloom & Brew about shipping.", False),                                  # other store
])
def test_grounding_rejects_fabrications(reply, ok):
    assert Assistant.grounded(StoreId.STORE_A, reply, GROUND_CTX, GROUND_DRAFT, "en", message="How much is shipping?",
                              catalog_names=CATALOG) is ok


def test_final_check_rebuilds_products_from_the_catalogue(client):
    assistant = client.app.state.assistant
    result = ChatResult(reply="Here you go.", intents=["product"], source="llm",
                        products=[{"slug": "daytrip-22l-daypack", "name": "Daytrip", "price": "$1.00", "price_cents": 100},
                                  {"slug": "everest-parka", "name": "Everest Parka", "price": "$9.00"}],
                        actions=[{"type": "add_to_cart", "slug": "everest-parka", "quantity": 1, "label": "Add"},
                                 {"type": "add_to_cart", "slug": "basecamp-4p-tent", "quantity": 1, "label": "Add"},   # out of stock
                                 {"type": "add_to_cart", "slug": "lumen-300-headlamp", "quantity": 1, "label": "Add"},
                                 {"type": "link", "to": "/cart", "label": "Cart"}])
    out = assistant._finalise(StoreId.STORE_A, result, "en", "Summit Trail Co.")
    assert [p["slug"] for p in out.products] == ["daytrip-22l-daypack"]
    assert out.products[0]["price"] == "$79.00" and out.products[0]["name"] == "Daytrip 22L Daypack"
    assert [a.get("slug") or a["type"] for a in out.actions] == ["lumen-300-headlamp", "link"]


def test_product_from_the_other_store_is_never_shown(client):
    assistant = client.app.state.assistant
    result = ChatResult(reply="ok", intents=["product"], source="rules", products=[{"slug": "gooseneck-kettle"}])
    assert assistant._finalise(StoreId.STORE_A, result, "en", "Summit Trail Co.").products == []


# =========================================================================================================
# H2 — placeholders never reach customers; rupee budgets are understood and never silently converted
# =========================================================================================================
@pytest.mark.parametrize("text, amount, currency", [
    ("Show me a backpack under ₹5000", 500000, "INR"),
    ("backpack under Rs. 5000", 500000, "INR"),
    ("INR 5000 backpack", 500000, "INR"),
    ("anything under 5000 rupees", 500000, "INR"),
    ("below ₹5,000", 500000, "INR"),
    ("tent within 1,00,000 rupees", 10000000, "INR"),
    ("5000 ரூபாய்க்குள் பை", 500000, "INR"),
    ("5000 रुपये से कम बैग", 500000, "INR"),
    ("Recommend a backpack under $100", 10000, "USD"),
    ("under 100 dollars", 10000, "USD"),
    ("budget of $49.50", 4950, "USD"),
    ("tent under 300", 30000, None),
])
def test_budget_parsing(text, amount, currency):
    b = parse_budget(text)
    assert b is not None and (b.amount_minor, b.currency) == (amount, currency)


@pytest.mark.parametrize("text", ["lighter, under 2 kg", "can you deliver within 3 days", "up to 4 people", "a 22L daypack"])
def test_quantities_and_units_are_not_budgets(text):
    assert parse_budget(text) is None


def test_rupee_amounts_are_formatted_in_indian_style():
    assert format_amount(500000, "INR") == "₹5,000" and format_amount(10000000, "INR") == "₹1,00,000"
    assert format_amount(4950, "USD") == "$49.50"


@pytest.mark.parametrize("lang, message, marker", [
    ("en", "Show me a backpack under ₹5000", "I won't guess an exchange rate"),
    ("ta", "₹5000-க்குள் பேக்பேக் இருக்கிறதா?", "நாணய மாற்று விகிதத்தை நான் ஊகிக்க மாட்டேன்"),
    ("hi", "5000 रुपये से कम बैकपैक दिखाओ", "विनिमय दर का अंदाज़ा नहीं लगाऊँगा"),
])
def test_rupee_budget_against_dollar_catalogue_is_explained_not_converted(client, lang, message, marker):
    body = ask(client, "store-a", message)
    assert body["language"] == lang
    assert marker in body["reply"] and "₹5,000" in body["reply"] and "USD" in body["reply"]
    assert not truth.has_placeholder(body["reply"])
    slugs = {p["slug"] for p in body["products"]}
    assert "daytrip-22l-daypack" in slugs   # real matches shown (unfiltered), with their USD prices


def test_dollar_budget_is_still_applied(client):
    body = ask(client, "store-a", "Recommend a backpack under $100")
    assert [p["slug"] for p in body["products"]] == ["daytrip-22l-daypack"]
    assert "exchange rate" not in body["reply"]


def test_model_placeholder_reply_is_replaced(settings):
    with make_client(settings, llm=ScriptedLLM("Shipping info is here: [insert login link]")) as c:
        body = ask(c, "store-a", "How long does shipping take?")
    assert body["source"] == "rules" and "[" not in body["reply"]


def test_final_check_blocks_any_placeholder(client):
    result = ChatResult(reply="Please click {login_url} to continue", intents=[], source="rules")
    out = client.app.state.assistant._finalise(StoreId.STORE_A, result, "en", "Summit Trail Co.")
    assert "{" not in out.reply and "Summit Trail Co." in out.reply


def test_no_template_renders_a_placeholder():
    filler = defaultdict(lambda: "X1")
    for key, langs in i18n.T.items():
        for lang, template in langs.items():
            text = template.format_map(filler)
            assert not truth.has_placeholder(text), (key, lang, text)


# =========================================================================================================
# H3 — search correctness
# =========================================================================================================
def test_backpack_under_100_finds_the_daypack(client):
    body = ask(client, "store-a", "Recommend a backpack under $100")
    assert [p["slug"] for p in body["products"]] == ["daytrip-22l-daypack"]
    assert "Daytrip 22L Daypack — $79.00" in body["reply"] and "don't have" not in body["reply"]


@pytest.mark.parametrize("store, q, expected", [
    ("store-a", "backpack", {"daytrip-22l-daypack", "trailhead-55l-backpack"}),
    ("store-a", "flashlight", {"lumen-300-headlamp"}),
    ("store-a", "hiking shoes", {"granite-hiking-boots"}),
    ("store-b", "pour over", {"ceramic-pour-over-dripper"}),
    ("store-b", "coffee mill", {"precision-burr-grinder"}),
])
def test_storefront_search_handles_everyday_words(client, store, q, expected):
    slugs = {p["slug"] for p in client.get(f"/api/stores/{store}/products", params={"q": q}).json()["products"]}
    assert expected <= slugs, slugs


def test_storefront_search_respects_category_and_store(client):
    r = client.get("/api/stores/store-a/products", params={"q": "pack", "category": "Packs"}).json()["products"]
    assert r and all(p["category"] == "Packs" for p in r)
    assert client.get("/api/stores/store-a/products", params={"q": "kettle"}).json()["products"] == []


def test_bloom_and_brew_budget_search(client):
    body = ask(client, "store-b", "Do you have a kettle under $100?")
    assert [p["slug"] for p in body["products"]] == ["gooseneck-kettle"]
    none = ask(client, "store-b", "Do you have a grinder under $100?")
    assert none["products"] == [] and "within $100.00" in none["reply"]


# =========================================================================================================
# H5 — phone order lookup privacy
# =========================================================================================================
def phone_turn(c, cid, **kw):
    return c.post(f"/api/phone/simulator/calls/{cid}/turns", json=kw)


def test_simulator_does_not_exist_unless_enabled(settings):
    with make_client(settings, phone_simulator_enabled=False) as c:
        assert c.post("/api/phone/simulator/store-a/calls").status_code == 404
        assert phone_turn(c, "abcdefghijklmnop", speech="hi").status_code == 404


def test_simulator_is_off_by_default_outside_development():
    from app.config import load_settings
    from pathlib import Path
    base = {"APP_ENV": "production", "APP_SECRET_KEY": "x" * 48, "CORS_ORIGINS": "https://shop.example",
            "STORE_A_DATABASE_URL": "postgresql://a:b@127.0.0.1:1/store_a", "STORE_B_DATABASE_URL": "postgresql://a:b@127.0.0.1:1/store_b"}
    assert load_settings(base, env_file=Path("/nonexistent")).phone_simulator_enabled is False
    assert load_settings({**base, "APP_ENV": "development"}, env_file=Path("/nonexistent")).phone_simulator_enabled is True
    assert load_settings({**base, "PHONE_SIMULATOR_ENABLED": "true"}, env_file=Path("/nonexistent")).phone_simulator_enabled is True


def test_guessing_across_calls_is_blocked_without_revealing_a_correct_guess(settings):
    """Wrong postal codes for one order from MANY callers (distinct identities via a trusted proxy), spread over many
    calls, lock that order once the shared per-order budget is used up — even the RIGHT code is then refused with the
    same message, so a guesser can't tell when they succeed. (Phase 1.1: tiered limits; see phone/session.py.)"""
    with make_client(settings, trusted_proxies=("testclient",)) as c:
        for i in range(phone_session.MAX_FAILURES_PER_ORDER):
            who = {"X-Forwarded-For": f"203.0.113.{i + 1}"}
            cid = c.post("/api/phone/simulator/store-a/calls", headers=who).json()["call_id"]
            c.post(f"/api/phone/simulator/calls/{cid}/turns", json={"speech": "track order SA-10001"}, headers=who)
            r = c.post(f"/api/phone/simulator/calls/{cid}/turns", json={"digits": "00000"}, headers=who).json()
            assert "shipped" not in r["say"]
        fresh = {"X-Forwarded-For": "198.51.100.77"}   # a new caller with the RIGHT code
        cid = c.post("/api/phone/simulator/store-a/calls", headers=fresh).json()["call_id"]
        c.post(f"/api/phone/simulator/calls/{cid}/turns", json={"speech": "track order SA-10001"}, headers=fresh)
        right = c.post(f"/api/phone/simulator/calls/{cid}/turns", json={"digits": "80302"}, headers=fresh).json()
    assert right["hang_up"] is True and "shipped" not in right["say"] and "can't verify orders by phone" in right["say"]


def test_per_caller_limit_spans_different_orders(client):
    numbers = ["SA-10002", "SA-10003", "SA-10004", "SA-10005", "SA-10001"]
    for n in numbers:
        cid = client.post("/api/phone/simulator/store-a/calls").json()["call_id"]
        phone_turn(client, cid, speech=f"track order {n}")
        phone_turn(client, cid, digits="11111")
    cid = client.post("/api/phone/simulator/store-a/calls").json()["call_id"]
    phone_turn(client, cid, speech="track order SA-10001")
    assert "can't verify orders by phone" in phone_turn(client, cid, digits="80302").json()["say"]


def test_starting_calls_is_rate_limited(client):
    codes = [client.post("/api/phone/simulator/store-b/calls").status_code for _ in range(phone_session.MAX_CALLS_PER_CALLER + 1)]
    assert codes[:-1] == [200] * phone_session.MAX_CALLS_PER_CALLER and codes[-1] == 429


def test_correct_verification_still_works_for_a_legitimate_caller(client):
    cid = client.post("/api/phone/simulator/store-a/calls").json()["call_id"]
    phone_turn(client, cid, speech="track order SA-10001")
    assert "SA-10001 is shipped" in phone_turn(client, cid, digits="80302").json()["say"]


def test_chat_never_reveals_whether_someone_elses_order_exists(client):
    jordan = login(client, "store-a", JORDAN, PW_A)
    other = ask(client, "store-a", "Where is order SA-10001?", jordan)["reply"]   # Alex's real order
    fake = ask(client, "store-a", "Where is order SA-99999?", jordan)["reply"]    # does not exist
    assert other.replace("SA-10001", "N") == fake.replace("SA-99999", "N")
    assert "1ZDEMO" not in other


# =========================================================================================================
# Cancellation — eligible, ineligible, repeated, not yours
# =========================================================================================================
def test_cancel_eligible_then_repeat_is_refused_and_stock_is_released_once(client):
    headers, number = place_order(client)
    from tests.conftest import db_exec
    before = db_exec(client.app.state.settings, "store-a", "SELECT stock_qty FROM products WHERE slug = 'lumen-300-headlamp'")[0][0]
    ok = client.post(f"/api/stores/store-a/orders/{number}/cancel", headers=headers)
    assert ok.status_code == 200 and ok.json()["order"]["status"] == "cancelled"
    again = client.post(f"/api/stores/store-a/orders/{number}/cancel", headers=headers)
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_cancelled"
    after = db_exec(client.app.state.settings, "store-a", "SELECT stock_qty FROM products WHERE slug = 'lumen-300-headlamp'")[0][0]
    assert after == before + 1


def test_paid_order_cannot_be_cancelled_online(client):
    headers, number = place_order(client)
    pay = client.post(f"/api/stores/store-a/orders/{number}/payments", headers=headers).json()["payment"]
    client.post(f"/api/stores/store-a/payments/sandbox/{pay['reference']}/complete", headers=headers, json={"outcome": "success"})
    client.post(f"/api/stores/store-a/orders/{number}/payments/verify", headers=headers)
    r = client.post(f"/api/stores/store-a/orders/{number}/cancel", headers=headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_state"


def test_cannot_cancel_someone_elses_order(client):
    _, number = place_order(client)
    alex = login(client, "store-a", ALEX, PW_A)
    r = client.post(f"/api/stores/store-a/orders/{number}/cancel", headers=alex)
    assert r.status_code == 404
    store_b = login(client, "store-b", MARIA, PW_B)
    assert client.post(f"/api/stores/store-a/orders/{number}/cancel", headers=store_b).status_code == 403


def test_chat_cancel_is_only_proposed_never_performed(client):
    headers, number = place_order(client)
    body = ask(client, "store-a", f"Cancel my order {number}", headers)
    assert any(a["type"] == "cancel_order" and a["order_number"] == number for a in body["actions"])
    order = client.get(f"/api/stores/store-a/orders/{number}", headers=headers).json()["order"]
    assert order["status"] == "pending_payment"   # nothing happens until the customer confirms in the UI


# =========================================================================================================
# Support tickets — no ticket system exists, so none is ever "created"
# =========================================================================================================
@pytest.mark.parametrize("store, email", [("store-a", EMAIL_A), ("store-b", EMAIL_B)])
@pytest.mark.parametrize("lang, message, marker", [
    ("en", "Create a support ticket for me", "no ticket system"),
    ("ta", "எனக்கு ஒரு டிக்கெட் உருவாக்குங்கள்", "டிக்கெட் அமைப்பு இல்லை"),
    ("hi", "मेरे लिए एक टिकट बनाइए", "कोई टिकट सिस्टम नहीं"),
])
def test_ticket_requests_are_answered_honestly(client, store, email, lang, message, marker):
    body = ask(client, store, message)
    assert body["language"] == lang and "ticket" in body["intents"]
    assert marker in body["reply"] and email in body["reply"]
    assert not re.search(r"ticket (has been|was) created|ticket number is|#\d{3,}", body["reply"], re.I)
    assert any(a["type"] == "link" and a["to"] == f"mailto:{email}" for a in body["actions"])


def test_ticket_intent_is_not_a_product_search():
    assert detect_intent("Create a support ticket for me").intents == {"ticket"}

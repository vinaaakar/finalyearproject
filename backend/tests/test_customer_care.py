"""Customer-care assistant: intents, verified answers, proposed (never self-performed) actions, privacy,
escalation and honesty about unsupported capabilities — in Tamil, English and Hindi, for Scout and Maple.
Runs against the *_test databases with the LLM off unless a test installs a fake one."""

import re

import pytest

from app.assistant.intent import detect_intent, sensitive_kind
from tests.conftest import (ADDRESS_A, ADDRESS_B, AGENT_A, ALEX, MARIA, PW_A, PW_AGENT, PW_B, idem, login, make_client,
                            new_customer, set_stock)
from tests.test_assistant import FakeLLM

LAMP, JACKET, STOVE = "lumen-300-headlamp", "stormshell-rain-jacket", "pocketflame-stove"
HONEY = "wildflower-honey"
EMAIL_A, EMAIL_B = "help@summittrail.example.com", "care@bloomandbrew.example.com"
TAMIL, DEVANAGARI = re.compile(r"[஀-௿]"), re.compile(r"[ऀ-ॿ]")


def ask(client, store, message, headers=None, history=None, channel="web_chat", conversation="en"):
    # Like the widget, send the current conversation language (used only for language-neutral messages).
    r = client.post(f"/api/stores/{store}/chat", headers=headers or {},
                    json={"message": message, "history": history or [], "channel": channel, "conversation_language": conversation})
    assert r.status_code == 200, r.text
    return r.json()


def turns(*pairs):
    return [{"role": role, "content": text} for role, text in pairs]


def place_order(client, store="store-a", slug=LAMP, qty=1):
    """A new customer with one unpaid order (the normal checkout API)."""
    set_stock(client.app.state.settings, store, slug, 75 if store == "store-a" else 64)
    headers, _ = new_customer(client, store)
    client.post(f"/api/stores/{store}/cart/items", json={"slug": slug, "quantity": qty}, headers=headers)
    quote = client.post(f"/api/stores/{store}/checkout/quote", json={"shipping_method": "standard"}, headers=headers).json()["cart"]
    r = client.post(f"/api/stores/{store}/checkout", headers={**headers, **idem()},
                    json={"shipping": ADDRESS_A if store == "store-a" else ADDRESS_B, "expected_total_cents": quote["total_cents"]})
    assert r.status_code == 201, r.text
    return headers, r.json()["order"]["order_number"]


# ---- intent detection --------------------------------------------------------------------------
@pytest.mark.parametrize("message, expected", [
    ("Where's my parcel?", "order_status"),
    ("My order hasn't come yet.", "order_late"),
    ("I paid, but nothing happened.", "payment_issue"),
    ("I want to return this.", "return_request"),
    ("Do you have something cheaper?", "cheaper"),
    ("இந்த ஆர்டர் எப்போது வரும்?", "order_status"),
    ("எனக்கு ரீஃபண்ட் வரவில்லை.", "refund_status"),
    ("मेरा ऑर्डर कहाँ है?", "order_status"),
    ("मुझे रिफंड नहीं मिला।", "refund_status"),
    ("It says delivered but I never got it", "delivered_missing"),
    ("My order arrived damaged", "damaged"),
    ("என் பூட்ஸ் சேதமடைந்து வந்தது", "damaged"),
    ("I got the wrong item", "wrong_item"),
    ("Can I cancel my order?", "cancel"),
    ("ஆர்டரை ரத்து செய்ய முடியுமா?", "cancel"),
    ("मुझे ऑर्डर रद्द करना है", "cancel"),
    ("Can I change my delivery address?", "modify_order"),
    ("Was I charged twice?", "payment_issue"),
    ("Compare the Ridgeline and Basecamp tents", "compare"),
    ("add 2 headlamps to my cart", "add_to_cart"),
    ("कार्ट में दो हेडलैंप डाल दो", "add_to_cart"),
    ("Do you have a discount code?", "promotions"),
    ("Can I get an invoice?", "invoice"),
    ("I forgot my password", "account"),
    ("How do I check out as a guest?", "checkout_help"),
    ("the website is not working", "tech_issue"),
    ("This is useless!", "frustration"),
    ("I want to talk to a human", "contact"),
    ("What languages do you speak?", "languages"),
    ("I use a screen reader", "accessibility"),
    ("What do you do with my data?", "privacy"),
    ("Do you take bulk orders?", "bulk"),
    ("I want a refund", "return_request"),
    ("I want to order the same as last time", "reorder"),
    ("How do I store my tent?", "care"),
])
def test_everyday_phrasing_is_understood(message, expected):
    assert expected in detect_intent(message).intents


def test_intent_rules_avoid_false_matches():
    assert "order_late" not in detect_intent("I love chocolate").intents            # "late" inside a word
    assert "care" not in detect_intent("Tell me about Bloom & Brew").intents         # a store name, not "how to brew"
    assert "order_late" not in detect_intent("எனக்கு ரீஃபண்ட் வரவில்லை").intents     # refund, not a late parcel
    assert "defective" not in detect_intent("the checkout page is not working").intents
    assert detect_intent("add 2 headlamps to my cart").quantity == 2
    assert detect_intent("add the $39 headlamp").quantity == 1                       # a price is not a quantity


# ---- product discovery -------------------------------------------------------------------------
def test_comparison_uses_catalogue_facts(client):
    body = ask(client, "store-a", "Compare the Ridgeline and Basecamp tents")
    assert body["language"] == "en" and {p["slug"] for p in body["products"]} == {"ridgeline-2p-tent", "basecamp-4p-tent"}
    assert "$329.00" in body["reply"] and "$449.00" in body["reply"] and "$120.00 cheaper" in body["reply"]
    assert "out of stock" in body["reply"]                                            # Basecamp is sold out (seeded)


def test_out_of_stock_answer_suggests_an_in_stock_alternative(client):
    body = ask(client, "store-b", "Is the House Blend in stock?")
    assert "House Blend Whole Beans — $16.00, currently out of stock" in body["reply"]
    assert "Ethiopia Yirgacheffe Whole Beans" in body["reply"]


def test_cheaper_follow_up_uses_the_conversation_and_the_same_kind_of_product(client):
    hist = turns(("user", "Do you have a big backpack?"), ("assistant", "Here's what I found: Trailhead 55L Backpack — $219.00, in stock."))
    body = ask(client, "store-a", "Do you have something cheaper?", history=hist)
    assert "Daytrip 22L Daypack" in body["reply"] and "$79.00" in body["reply"]
    tent = turns(("user", "2-person tent?"), ("assistant", "Here's what I found: Ridgeline 2-Person Tent — $329.00, in stock."))
    body = ask(client, "store-a", "anything cheaper?", history=tent)
    assert "already the lowest-priced" in body["reply"] and "Backpack" not in body["reply"]
    # Without anything to compare against, ask instead of guessing.
    body = ask(client, "store-a", "Do you have something cheaper?")
    assert body["products"] == [] and "Which product" in body["reply"]


def test_care_tips_are_store_specific_and_labelled_as_general_advice(client):
    a = ask(client, "store-a", "How do I store my tent?")
    assert a["reply"].startswith("General tip") and "dry" in a["reply"]
    b = ask(client, "store-b", "How do I store my tent?")
    assert "don't have reliable care" in b["reply"] and EMAIL_B in b["reply"]
    ta = ask(client, "store-b", "பச்சை தேநீர் தயாரிப்பது எப்படி?")
    assert ta["language"] == "ta" and "70–80 °C" in ta["reply"] and TAMIL.search(ta["reply"])


# ---- add to cart: proposed only, performed by the cart API --------------------------------------
def test_add_to_cart_is_proposed_not_performed(client):
    set_stock(client.app.state.settings, "store-a", LAMP, 75)
    headers, _ = new_customer(client, "store-a")
    body = ask(client, "store-a", "Add 2 headlamps to my cart", headers)
    assert body["actions"] == [{"type": "add_to_cart", "slug": LAMP, "name": "Lumen 300 Headlamp", "quantity": 2,
                                "label": "Add 2 × Lumen 300 Headlamp to cart"}]
    assert "Tap" in body["reply"] and "added" not in body["reply"].lower().split("tap")[0]
    # Nothing was added by the chat itself.
    assert client.get("/api/stores/store-a/cart", headers=headers).json()["cart"]["items"] == []


def test_add_to_cart_respects_stock_limits_and_sold_out_items(client):
    s = client.app.state.settings
    set_stock(s, "store-a", JACKET, 3)
    body = ask(client, "store-a", "Add 5 rain jackets to my cart")
    assert "up to 3" in body["reply"] and body["actions"][0]["quantity"] == 3
    body = ask(client, "store-a", "Add the Basecamp 4-Person Tent to my cart")
    assert body["actions"] == [] and "out of stock" in body["reply"] and "Ridgeline" in body["reply"]


def test_add_to_cart_follow_up_and_ambiguity(client):
    hist = turns(("assistant", "Here's what I found: Classic French Press — $34.00, in stock."))
    body = ask(client, "store-b", "add it to my cart", history=hist)
    assert body["actions"][0]["slug"] == "classic-french-press"
    body = ask(client, "store-b", "add some coffee beans to my cart")
    assert body["actions"] == [] and "Which one" in body["reply"]                    # two kinds of beans: ask


def test_staff_accounts_get_no_shopping_actions(client):
    agent = login(client, "store-a", AGENT_A, PW_AGENT)
    body = ask(client, "store-a", "add the headlamp to my cart", agent)
    assert body["actions"] == [] and "Staff accounts can't shop" in body["reply"]


# ---- orders: authentication, ownership, isolation ---------------------------------------------
@pytest.mark.parametrize("message, lang", [
    ("My order hasn't come yet.", "en"), ("இந்த ஆர்டர் எப்போது வரும்?", "ta"), ("मेरा ऑर्डर कहाँ है?", "hi"),
    ("Can I cancel my order?", "en"), ("I paid but nothing happened", "en"), ("मुझे रिफंड नहीं मिला।", "hi"),
    ("It says delivered but it never came", "en"), ("எனக்கு ரீஃபண்ட் வரவில்லை.", "ta"),
])
def test_private_order_questions_need_sign_in(client, message, lang):
    body = ask(client, "store-a", message)
    assert body["requires_login"] is True and body["orders"] == [] and body["language"] == lang
    assert not re.search(r"\b(SA|BB)-\d{5}\b", body["reply"])
    assert not any(a["type"] in ("cancel_order", "add_to_cart") for a in body["actions"])


def test_delivery_answers_use_only_the_customers_own_orders(client):
    alex = login(client, "store-a", ALEX, PW_A)
    body = ask(client, "store-a", "My order hasn't come yet.", alex)
    assert [o["order_number"] for o in body["orders"]] == ["SA-10001"]
    assert "UPS" in body["reply"] and "1ZDEMO0000000001" in body["reply"] and EMAIL_A in body["reply"]
    # Another customer's order and another store's order look exactly like unknown orders.
    for number in ("SA-10003", "BB-20001"):
        body = ask(client, "store-a", f"It says delivered but I never got {number}", alex)
        assert body["orders"] == [] and f"couldn't find order {number}" in body["reply"]
        assert "Jordan" not in body["reply"] and "97205" not in body["reply"]


def test_delivered_but_missing_gives_steps_without_promising_an_investigation(client):
    alex = login(client, "store-a", ALEX, PW_A)
    body = ask(client, "store-a", "SA-10002 says delivered but it never arrived", alex)
    assert "marked as delivered" in body["reply"] and "I can't open an investigation" in body["reply"]
    assert {"type": "link", "to": f"mailto:{EMAIL_A}", "label": f"Email {EMAIL_A}"} in body["actions"]


def test_follow_up_question_reuses_the_order_from_the_conversation(client):
    alex = login(client, "store-a", ALEX, PW_A)
    hist = turns(("user", "Where is SA-10001?"), ("assistant", "Order SA-10001 is shipped via UPS."))
    body = ask(client, "store-a", "When will it arrive?", alex, history=hist)
    assert [o["order_number"] for o in body["orders"]] == ["SA-10001"]


def test_a_new_question_does_not_reuse_an_old_order_from_the_conversation(client):
    alex = login(client, "store-a", ALEX, PW_A)
    hist = turns(("user", "Where is SA-10002?"), ("assistant", "Order SA-10002 is delivered on 2026-10-19."))
    # Curly apostrophe (phones, macOS) and no "it"/"this": about the customer's orders in general.
    body = ask(client, "store-a", "My order hasn’t come yet", alex, history=hist)
    assert "order_late" in body["intents"] and [o["order_number"] for o in body["orders"]] == ["SA-10001"]


def test_cross_store_session_is_rejected_for_care_questions(client):
    alex_a = login(client, "store-a", ALEX, PW_A)
    r = client.post("/api/stores/store-b/chat", headers=alex_a, json={"message": "Has my refund come through?"})
    assert r.status_code == 403


# ---- cancellation: confirmed, performed by the existing API -------------------------------------
def test_cancellation_is_offered_only_for_unpaid_orders_and_needs_confirmation(client):
    headers, number = place_order(client)
    body = ask(client, "store-a", "I want to cancel my order", headers)
    assert body["actions"] == [{"type": "cancel_order", "order_number": number, "label": f"Cancel order {number}"}]
    assert "isn't cancelled until you confirm" in body["reply"]
    assert client.get(f"/api/stores/store-a/orders/{number}", headers=headers).json()["order"]["status"] == "pending_payment"
    # The customer confirms in the UI, which calls the existing endpoint.
    assert client.post(f"/api/stores/store-a/orders/{number}/cancel", headers=headers).json()["order"]["status"] == "cancelled"
    body = ask(client, "store-a", f"cancel {number}", headers)
    assert body["actions"] == [] and "already cancelled" in body["reply"]
    # A shipped order cannot be cancelled, and no cancel button is offered.
    alex = login(client, "store-a", ALEX, PW_A)
    body = ask(client, "store-a", "Can I cancel SA-10001?", alex)
    assert body["actions"] == [] and "can no longer be cancelled" in body["reply"]


def test_cancellation_asks_which_order_when_there_are_several(client):
    headers, first = place_order(client)
    client.post("/api/stores/store-a/cart/items", json={"slug": STOVE, "quantity": 1}, headers=headers)
    quote = client.post("/api/stores/store-a/checkout/quote", json={"shipping_method": "standard"}, headers=headers).json()["cart"]
    second = client.post("/api/stores/store-a/checkout", headers={**headers, **idem()},
                         json={"shipping": ADDRESS_A, "expected_total_cents": quote["total_cents"]}).json()["order"]["order_number"]
    body = ask(client, "store-a", "cancel my order", headers)
    assert body["actions"] == [] and "Which order" in body["reply"] and first in body["reply"] and second in body["reply"]


# ---- payments ----------------------------------------------------------------------------------
def test_payment_failure_and_success_are_reported_from_verified_records(client):
    headers, number = place_order(client)
    pay = client.post(f"/api/stores/store-a/orders/{number}/payments", headers=headers).json()["payment"]
    client.post(f"/api/stores/store-a/payments/sandbox/{pay['reference']}/complete", headers=headers, json={"outcome": "decline"})
    client.post(f"/api/stores/store-a/orders/{number}/payments/verify", headers=headers)
    body = ask(client, "store-a", "My payment failed", headers)
    assert "was declined, so nothing was charged" in body["reply"] and "test mode" in body["reply"]
    assert {"type": "link", "to": f"/orders/{number}/pay", "label": f"Pay for order {number}"} in body["actions"]
    pay = client.post(f"/api/stores/store-a/orders/{number}/payments", headers=headers).json()["payment"]
    client.post(f"/api/stores/store-a/payments/sandbox/{pay['reference']}/complete", headers=headers, json={"outcome": "success"})
    client.post(f"/api/stores/store-a/orders/{number}/payments/verify", headers=headers)
    body = ask(client, "store-a", f"did my payment for {number} go through?", headers)
    assert f"The payment for order {number} ($45.95) is confirmed" in body["reply"]


def test_duplicate_charge_concern_is_escalated_not_resolved(client):
    headers, number = place_order(client)
    body = ask(client, "store-a", "I think I was charged twice", headers)
    assert "only one successful payment" in body["reply"] and "can't reverse charges" in body["reply"]
    assert any(a["to"] == f"mailto:{EMAIL_A}" for a in body["actions"] if a["type"] == "link")


# ---- refunds, returns, exchanges -----------------------------------------------------------------
def test_refund_status_is_never_invented(client):
    alex = login(client, "store-a", ALEX, PW_A)
    body = ask(client, "store-a", "Has my refund come through?", alex)
    assert "can't see a refund recorded" in body["reply"] and "returned and refunded" not in body["reply"]
    maria = login(client, "store-b", MARIA, PW_B)
    body = ask(client, "store-b", "Did my refund for BB-20004 come through?", maria)
    # C1: a returned order is not proof of a refund (no refund records exist), so nothing may say it was refunded.
    assert "Order BB-20004 is marked as returned" in body["reply"] and "can't see a refund record" in body["reply"]
    assert "refunded" not in body["reply"].lower().replace("haven't been refunded", "")
    hi = ask(client, "store-b", "मुझे रिफंड नहीं मिला।", maria)
    assert hi["language"] == "hi" and "BB-20004" in hi["reply"] and DEVANAGARI.search(hi["reply"])


def test_return_answers_use_each_stores_own_policy_and_delivery_date(client):
    alex = login(client, "store-a", ALEX, PW_A)
    body = ask(client, "store-a", "I want to return my boots", alex)
    assert "Order SA-10002 was delivered on" in body["reply"] and "60-day policy" in body["reply"]
    # A return request is now registered from the chat (care_flow.py): it asks for what's missing, nothing is submitted yet.
    assert body["care_draft"]["kind"] == "return" and body["care_draft"]["order"] == "SA-10002" and body["care_reference"] is None
    b = ask(client, "store-b", "How do I return an item?")
    assert "30 days" in b["reply"] and "60" not in b["reply"]


# ---- accounts, checkout, unsupported capabilities -----------------------------------------------
def test_account_and_checkout_help(client):
    body = ask(client, "store-a", "I forgot my password")
    assert {"type": "link", "to": "/forgot-password", "label": "Reset password"} in body["actions"]
    assert "never ask for your password" in body["reply"]
    body = ask(client, "store-a", "How do I check out as a guest?")
    assert "no guest checkout" in body["reply"] and "your cart is kept" in body["reply"].lower()
    assert "Alaska & Hawaii" in body["reply"]
    body = ask(client, "store-b", "How do I check out as a guest?")
    assert "Hawaii" not in body["reply"]                                              # Bloom & Brew ships to all states
    body = ask(client, "store-a", "Why can't I ship to Hawaii?")
    assert "doesn't ship to Alaska & Hawaii" in body["reply"] and "To check out" not in body["reply"]


@pytest.mark.parametrize("message, must, forbidden", [
    ("Do you have a discount code?", "no promotions or discount codes", ["applied to your", "here's a code"]),
    ("Can I get an invoice for my order?", "Invoices aren't available", ["invoice is attached", "I've sent"]),
    ("Can I change my delivery address?", "can't be changed once they're placed", ["address has been updated", "I've changed"]),
    ("Please delete my account", "isn't available online", ["has been deleted", "I've deleted"]),
])
def test_unsupported_capabilities_are_explained_honestly(client, message, must, forbidden):
    alex = login(client, "store-a", ALEX, PW_A)
    body = ask(client, "store-a", message, alex)
    assert must in body["reply"]
    assert not any(f.lower() in body["reply"].lower() for f in forbidden)


# ---- people, frustration, repeated failures ------------------------------------------------------
def test_human_request_is_honest_and_summarises_the_problem(client):
    hist = turns(("user", "My headlamp stopped working after a week"), ("assistant", "I'm sorry it isn't working properly."))
    body = ask(client, "store-a", "I want to talk to a human", history=hist)
    # Signed out: a human-help request can be recorded only for an account; the store's contact is offered, and the
    # reply never pretends someone is live. (Signed in, the request is registered: tests/test_care_assistant.py.)
    assert "sign in" in body["reply"] and "Nobody is live in this chat" in body["reply"] and body["requires_login"]
    assert EMAIL_A in body["reply"] and "Mon–Fri 8am–6pm MT" in body["reply"]          # from the store profile
    assert not re.search(r"ticket (has been|was) created|agent will (call|contact)|callback", body["reply"], re.I)


def test_frustration_is_acknowledged_in_the_customers_language(client):
    body = ask(client, "store-b", "यह बहुत बेकार है, कुछ काम नहीं करता")
    assert body["language"] == "hi" and body["reply"].startswith("माफ़ कीजिए") and EMAIL_B in body["reply"]


def test_repeated_generic_answers_escalate_instead_of_repeating(client):
    first = ask(client, "store-a", "blah")
    second = ask(client, "store-a", "hmm what", history=turns(("user", "blah"), ("assistant", first["reply"])))
    assert second["reply"] != first["reply"] and EMAIL_A in second["reply"]


def test_unrelated_question_is_redirected_to_the_store(client):
    body = ask(client, "store-b", "What's the weather tomorrow?")
    assert "I'm Maple" in body["reply"] and "coffee, tea" in body["reply"]


# ---- secrets are never requested, used or forwarded ----------------------------------------------
def test_card_numbers_and_passwords_are_flagged_and_never_sent_to_the_model(settings):
    assert sensitive_kind("my card is 4111 1111 1111 1111") == "card"
    assert sensitive_kind("order SA-10001 for $329.00") is None
    fake = FakeLLM()
    with make_client(settings, llm=fake) as c:
        body = ask(c, "store-a", "My card number is 4111 1111 1111 1111 and the payment failed")
        assert "Please don't share card numbers" in body["reply"] and "4111" not in body["reply"]
        assert fake.calls == []
        # An earlier message with a password is not forwarded with later questions either.
        # (A policy question: product questions no longer go to the model at all.)
        ask(c, "store-a", "How long does shipping take?", history=turns(("user", "my password is Hunter2Hunter2")))
    assert fake.calls and "Hunter2Hunter2" not in str(fake.calls)


def test_care_answers_never_use_the_model(settings):
    fake = FakeLLM()
    with make_client(settings, llm=fake) as c:
        for m in ("Can I cancel my order?", "I want a refund", "Add a headlamp to my cart", "I want to talk to a human",
                  "What's the weather tomorrow?"):
            ask(c, "store-a", m)
    assert fake.calls == []


# ---- languages and voice ------------------------------------------------------------------------
def test_actions_and_replies_follow_the_customers_language(client):
    hi = ask(client, "store-a", "कार्ट में दो हेडलैंप डाल दो")
    assert hi["language"] == "hi" and hi["actions"][0]["label"] == "2 × Lumen 300 Headlamp कार्ट में जोड़ें"
    ta = ask(client, "store-a", "ஹெட்லேம்ப் ஒன்றை கார்ட்டில் சேர்க்கவும்")
    assert ta["language"] == "ta" and ta["actions"][0]["label"].endswith("கார்ட்டில் சேர்")
    for body in (hi, ta):
        assert "Lumen 300 Headlamp" in body["reply"] and "$39.00" in body["reply"]   # facts unchanged


def test_voice_channel_gets_the_same_verified_answer(client):
    alex = login(client, "store-a", ALEX, PW_A)
    typed = ask(client, "store-a", "My order hasn't come yet.", alex)
    spoken = ask(client, "store-a", "My order hasn't come yet.", alex, channel="web_voice")
    assert spoken["reply"] == typed["reply"] and spoken["orders"] == typed["orders"]

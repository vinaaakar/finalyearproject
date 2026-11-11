"""Regression tests for the defects verified in the final audit (India configuration, both stores, *_test databases):

- P0 "the cheapest X" = the lowest-priced in-stock product of that kind (a sleeping bag is never a daypack or a pad),
  in Tamil, English and Hindi; an out-of-stock cheaper item is never offered as available.
- P1 "What did I pay?" answers with the customer's own recorded order amount, without unrelated product suggestions.
- P1 English delivery-time questions keep the rule-based answer when the model's reply is unhelpful.
- P1 natural English attribute questions ("How much does it weigh?") use the catalogue text only.
- P1 the phone simulator asks for a six-digit PIN code for Indian orders, ZIP for US orders.
"""

from __future__ import annotations

import pytest

from .conftest import db_exec, new_customer, set_stock
from .test_care_assistant import Chat
from .test_care_requests import c, demo_list, order  # noqa: F401  (fixtures and the order helper)

STOCK = {"store-a": ("alpine-20f-sleeping-bag", "featherlite-sleeping-pad", "daytrip-22l-daypack", "trailhead-55l-backpack"),
         "store-b": ("house-blend-beans", "ethiopia-yirgacheffe-beans", "sencha-green-tea", "spiced-chai-blend")}


@pytest.fixture(autouse=True)
def known_stock(settings):
    """Stock levels these tests rely on (test databases only), put back afterwards."""
    before = {(s, slug): db_exec(settings, s, "SELECT stock_qty FROM products WHERE slug = %s", [slug])[0][0]
              for s, slugs in STOCK.items() for slug in slugs}
    for (s, slug) in before:
        set_stock(settings, s, slug, 0 if slug == "house-blend-beans" else 25)
    yield
    for (s, slug), qty in before.items():
        set_stock(settings, s, slug, qty)


def ask(c, store, message, lang="en", h=None):
    return Chat(c, store, h, lang).say(message)


# ---- P0: cheapest product of the requested kind --------------------------------------------------------------------
@pytest.mark.parametrize("message,lang", [
    ("What's the cheapest sleeping bag?", "en"),
    ("Show me the lowest-priced sleeping bag", "en"),
    ("மிகவும் மலிவான தூங்கும் பை எது?", "ta"),
    ("सबसे सस्ता स्लीपिंग बैग कौन सा है?", "hi"),
])
def test_cheapest_sleeping_bag_is_the_sleeping_bag_never_a_pad_or_daypack(c, message, lang):
    j = ask(c, "store-a", message, lang)
    assert j["language"] == lang
    assert [p["slug"] for p in j["products"]] == ["alpine-20f-sleeping-bag"]
    assert "Alpine 20°F Sleeping Bag" in j["reply"] and "₹4,299.00" in j["reply"]
    for wrong in ("Daypack", "Sleeping Pad", "Backpack", "Cheaper than"):
        assert wrong not in j["reply"]


@pytest.mark.parametrize("message,lang", [
    ("What's the cheapest coffee?", "en"), ("What is the lowest-priced coffee?", "en"),
    ("மிகவும் மலிவான காபி எது?", "ta"), ("सबसे सस्ती कॉफ़ी कौन सी है?", "hi"),
])
def test_cheapest_coffee_skips_the_out_of_stock_house_blend(c, message, lang):
    j = ask(c, "store-b", message, lang)
    assert j["products"][0]["slug"] == "ethiopia-yirgacheffe-beans" and "₹849.00" in j["reply"]
    assert all(p["slug"] != "house-blend-beans" for p in j["products"])          # never offered as available
    if lang == "en":
        assert "House Blend Whole Beans (₹549.00) costs less but is out of stock" in j["reply"]


@pytest.mark.parametrize("message,lang", [
    ("What's the cheapest tea?", "en"), ("மிகவும் மலிவான தேநீர் எது?", "ta"), ("सबसे सस्ती चाय कौन सी है?", "hi"),
])
def test_cheapest_tea_is_the_chai_with_the_sencha_next(c, message, lang):
    j = ask(c, "store-b", message, lang)
    assert [p["slug"] for p in j["products"]] == ["spiced-chai-blend", "sencha-green-tea"]
    assert j["reply"].index("₹349.00") < j["reply"].index("₹449.00")


def test_cheapest_respects_a_rupee_budget_and_each_store_only_sees_its_own_catalogue(c):
    j = ask(c, "store-a", "Cheapest sleeping bag under ₹3,000?")
    assert j["reply"].startswith("Nothing of that kind is within ₹3,000.00.")                # honest: above the budget
    assert "Alpine 20°F Sleeping Bag — ₹4,299.00" in j["reply"] and "Sleeping Pad" not in j["reply"]
    j = ask(c, "store-a", "What's the cheapest coffee?")              # Summit Trail sells no coffee
    assert j["products"] == [] and "couldn't find a matching product at Summit Trail Co." in j["reply"]
    j = ask(c, "store-b", "What's the cheapest sleeping bag?")        # Bloom & Brew sells no sleeping bags (not "340 g bag" beans)
    assert j["products"] == [] and "couldn't find a matching product at Bloom & Brew" in j["reply"]
    j = ask(c, "store-b", "सबसे सस्ता स्लीपिंग बैग कौन सा है?", "hi")
    assert j["products"] == [] and j["language"] == "hi"


def test_cheaper_than_is_unchanged(c):
    j = ask(c, "store-a", "Is there anything cheaper than the Trailhead 55L Backpack?")
    assert "Cheaper than the Trailhead 55L Backpack" in j["reply"] and j["products"][0]["slug"] == "daytrip-22l-daypack"


# ---- P1: "What did I pay?" — the customer's own recorded order amount ---------------------------------------------
@pytest.mark.parametrize("store", ["store-a", "store-b"])
@pytest.mark.parametrize("message,lang", [
    ("What did I pay?", "en"), ("How much was my last order?", "en"), ("How much did I pay for my last order?", "en"),
    ("நான் எவ்வளவு பணம் செலுத்தினேன்?", "ta"), ("मैंने कितना भुगतान किया?", "hi"),
])
def test_what_did_i_pay_answers_the_recorded_amount_of_the_customers_own_latest_order(c, settings, store, message, lang):
    h, _ = new_customer(c, store)
    o = order(c, store, h, deliver=False)
    total = db_exec(settings, store, "SELECT total_cents, currency FROM orders WHERE order_number = %s", [o["number"]])[0]
    assert total[1].strip() == "INR"
    rupees = f"₹{total[0] // 100:,}.{total[0] % 100:02d}"
    j = ask(c, store, message, lang, h)
    assert j["language"] == lang and o["number"] in j["reply"] and rupees in j["reply"]
    assert j["products"] == []                                                   # no unrelated suggestions
    assert "order_amount" in j["intents"] and "product" not in j["intents"]
    if lang == "en":
        assert f"came to {rupees} in total" in j["reply"] and f"A payment of {rupees} is recorded" in j["reply"]


def test_order_amount_named_order_unpaid_order_signed_out_and_other_customers(c):
    h, _ = new_customer(c, "store-a")
    paid = order(c, "store-a", h, deliver=False)
    unpaid = order(c, "store-a", h, pay=False)
    j = ask(c, "store-a", "What did I pay?", "en", h)                           # the latest order: not paid yet
    assert unpaid["number"] in j["reply"] and "hasn't been paid yet" in j["reply"]
    j = ask(c, "store-a", f"What was the total of order {paid['number']}?", "en", h)
    assert paid["number"] in j["reply"] and "is recorded for it" in j["reply"]
    j = ask(c, "store-a", "What did I pay?")                                     # signed out: never an amount
    assert j["requires_login"] and "₹" not in j["reply"]
    other, _ = new_customer(c, "store-a")
    j = ask(c, "store-a", f"What was the total of order {paid['number']}?", "en", other)
    assert "₹" not in j["reply"] and paid["number"] in j["reply"]                 # "not found" — no amount leaks
    hb, _ = new_customer(c, "store-b")
    j = ask(c, "store-b", "What did I pay?", "en", hb)                            # no orders in this store
    assert "₹" not in j["reply"]


# ---- P1: natural English attribute questions, answered from the catalogue only -------------------------------------
@pytest.mark.parametrize("turns,slug,expected", [
    (["How heavy is the Ridgeline tent?"], "ridgeline-2p-tent", "the Ridgeline 2-Person Tent weighs 1.9 kg"),
    (["How much does the Ridgeline 2-person tent weigh?"], "ridgeline-2p-tent", "weighs 1.9 kg"),
    (["Tell me about the Featherlite sleeping pad", "What is its weight?"], "featherlite-sleeping-pad", "weighs 410 g"),
    (["Show me the Alpine sleeping bag", "How much does this bag weigh?"], "alpine-20f-sleeping-bag",
     "doesn't list the weight of the Alpine 20°F Sleeping Bag, so I won't guess"),          # not in the catalogue: no guess
    (["How much does the gooseneck kettle weigh?"], "gooseneck-kettle", "doesn't list the weight"),
])
def test_weight_questions_use_the_catalogue_figure_or_say_it_is_not_listed(c, turns, slug, expected):
    store = "store-b" if "kettle" in turns[0] else "store-a"
    chat = Chat(c, store, None, "en")
    for t in turns:
        j = chat.say(t)
    assert "attribute" in j["intents"] and [p["slug"] for p in j["products"]] == [slug] and expected in j["reply"]


def test_attribute_question_without_a_product_asks_which_and_suggests_nothing(c):
    j = ask(c, "store-a", "How heavy is this product?")
    assert "Which product's weight" in j["reply"] and j["products"] == []
    j = Chat(c, "store-a", None, "hi").say("Ridgeline 2-Person Tent दिखाइए")
    j = Chat(c, "store-a", None, "hi").say("Ridgeline टेंट का वज़न कितना है?")
    assert j["language"] == "hi" and "1.9 kg" in j["reply"]


# ---- P1: English delivery-time questions keep the rule-based answer ------------------------------------------------
class UnhelpfulLLM:
    """A fake local model that answers like the real one did in the audit."""

    def __init__(self, reply="We don't have that information. Please contact care@bloomandbrew.example.com for shipping details."):
        self.reply, self.calls = reply, []

    def is_available(self):
        return True

    def chat(self, messages):
        self.calls.append(messages)
        return self.reply


def india_client(settings, llm):
    import dataclasses

    from app.config import PROJECT_ROOT

    from .conftest import make_client
    s = dataclasses.replace(settings, store_markets={"store-a": "IN", "store-b": "IN"}, checkout_countries=("IN",),
                            shipping_config_dir=PROJECT_ROOT / "config" / "shipping")
    return make_client(s, llm=llm)


@pytest.mark.parametrize("store", ["store-a", "store-b"])
@pytest.mark.parametrize("question", ["How long does delivery take?", "How many days does shipping take?"])
def test_unhelpful_model_reply_never_replaces_the_delivery_time_rule(settings, store, question):
    fake = UnhelpfulLLM()
    with india_client(settings, fake) as c:
        j = Chat(c, store, None, "en").say(question)
    assert j["source"] == "rules" and "No delivery time is promised" in j["reply"]
    assert "don't have that information" not in j["reply"]


def test_a_grounded_model_reply_is_still_used_and_tamil_hindi_never_reach_the_model(settings):
    fake = UnhelpfulLLM("Standard delivery anywhere in India costs ₹149.00, free on orders of ₹4,999.00 or more. "
                        "No delivery time is promised.")
    with india_client(settings, fake) as c:
        j = Chat(c, "store-a", None, "en").say("How long does delivery take?")
        assert j["source"] == "llm" and j["reply"] == fake.reply
        calls = len(fake.calls)
        ta = Chat(c, "store-a", None, "ta").say("டெலிவரிக்கு எத்தனை நாள் ஆகும்?")
        hi = Chat(c, "store-a", None, "hi").say("डिलीवरी में कितने दिन लगते हैं?")
    assert len(fake.calls) == calls and ta["source"] == hi["source"] == "rules"
    assert "டெலிவரி நேரம் எதுவும் உறுதியளிக்கப்படவில்லை" in ta["reply"] and "डिलीवरी का कोई समय तय नहीं है" in hi["reply"]


# ---- P1: India phone simulator asks for the six-digit PIN code ------------------------------------------------------
def _turn(c, cid, **kw):
    r = c.post(f"/api/phone/simulator/calls/{cid}/turns", json=kw)
    assert r.status_code == 200, r.text
    return r.json()["say"]


@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_india_phone_verification_asks_for_the_six_digit_pin_and_verifies_an_indian_order(c, store):
    h, _ = new_customer(c, store)
    o = order(c, store, h, deliver=False)                                   # shipped to PIN 625521 (Cumbum, Tamil Nadu)
    cid = c.post(f"/api/phone/simulator/{store}/calls").json()["call_id"]
    say = _turn(c, cid, speech=f"Where is my order {o['number']}?")
    assert "six-digit shipping PIN code" in say and "five-digit shipping ZIP" not in say
    wrong = _turn(c, cid, digits="600001")
    assert "PIN code don't match" in wrong and "being prepared" not in wrong
    _turn(c, cid, speech=o["number"])
    assert f"Order {o['number']} is being prepared" in _turn(c, cid, digits="625521")


def test_us_market_phone_wording_is_unchanged(client):
    cid = client.post("/api/phone/simulator/store-a/calls").json()["call_id"]
    assert "order number" in _turn(client, cid, speech="I want to check my order")
    say = _turn(client, cid, digits="10001")
    assert "five-digit shipping ZIP code" in say and "PIN" not in say


# ---- found by scripts/evaluate_assistant.py: a Tamil refund phrasing was registered as a return ---------------------
@pytest.mark.parametrize("message,kind", [
    ("எனக்கு பணத்தைத் திருப்பித் தர வேண்டும்.", "refund"), ("என் பணத்தை திருப்பி கொடுங்கள்", "refund"),
    ("मेरे पैसे लौटा दो", "refund"), ("என் ஆர்டரைத் திருப்பி அனுப்ப வேண்டும்.", "return"), ("I want to request a refund.", "refund"),
])
def test_refund_and_return_wording_in_tamil_and_hindi(message, kind):
    from app.assistant.care_flow import detect
    assert detect(message) == {"kind": kind}


def test_tamil_refund_conversation_creates_a_refund_request(c):
    h, _ = new_customer(c, "store-b")
    o = order(c, "store-b", h)
    chat = Chat(c, "store-b", h, "ta")
    j = chat.say("எனக்கு பணத்தைத் திருப்பித் தர வேண்டும்.")
    assert chat.draft["kind"] == "refund" and chat.draft["order"] == o["number"]
    for answer in ("1", "பொருள் உடைந்த நிலையில் வந்தது.", "ஆம்"):
        j = chat.say(answer)
    assert j["care_reference"].startswith("BB-RFD-")


# ---- found by scripts/eval_llm.py: the model offered a phone line that does not exist --------------------------------
def test_model_reply_inventing_a_phone_line_is_rejected(settings):
    fake = UnhelpfulLLM("You can email help@summittrail.example.com, or give us a call during our support hours.")
    with india_client(settings, fake) as c:
        j = Chat(c, "store-a", None, "en").say("How can I contact you?")
    assert fake.calls and j["source"] == "rules" and "call" not in j["reply"].lower()
    assert "help@summittrail.example.com" in j["reply"]

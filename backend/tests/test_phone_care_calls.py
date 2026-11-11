"""Customer-care calls, end to end, as a caller uses them: the phone simulator (no real telephone network) in Tamil, English
and Hindi, on India-market orders created through the normal API (cart → checkout → sandbox payment → staff delivery).

What a caller must be able to do on the phone, and what must never happen:
- find out where an order is, after proving it is theirs (order number + shipping PIN code);
- record a complaint, a return request, a SIMULATED refund request or a request for the team — limited to that one verified
  order — and hear the reference the database returned (also spelled out), with an explicit "yes" before anything is saved;
- never be told they are being transferred to a person (there is no staffed line), never hear about other orders or requests;
- not be trapped in a question: silence, "operator", "cancel", another question, a language change, all work mid-flow;
- silence and sentences that merely contain a number never count as a wrong PIN guess.
"""

from __future__ import annotations

import re

import pytest

from app.phone import session as ps
from app.phone.phone_text import spelled, spoken_date

from .conftest import ALEX, PW_A, db_exec, login, new_customer
from .test_care_requests import agent, c, demo_list, order  # noqa: F401  (fixtures: India-market client + demo INR prices)

PIN = "625521"          # every order made by test_care_requests.order ships to Cumbum, Tamil Nadu


class Call:
    def __init__(self, client, store: str, language: str | None = None, headers: dict | None = None):
        self.c, self.headers = client, headers or {}
        r = client.post(f"/api/phone/simulator/{store}/calls", json={"language": language} if language else None, headers=self.headers)
        assert r.status_code == 200, r.text
        self.first = r.json()
        self.id = self.first["call_id"]

    def say(self, speech: str | None = None, digits: str | None = None) -> dict:
        body = {k: v for k, v in (("speech", speech), ("digits", digits)) if v is not None}
        r = self.c.post(f"/api/phone/simulator/calls/{self.id}/turns", json=body, headers=self.headers)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["simulated"] is True and out["transfer_to_agent"] is False
        return out

    def verify(self, number: str, pin: str = PIN) -> dict:
        self.say(number)
        return self.say(digits=pin)


def requests_of(c, store, h):
    return c.get(f"/api/stores/{store}/care/requests", headers=h).json()["requests"]


def guard_failures(c, store, order_number):
    return c.app.state.calls.guard.count(("fail-order", store, order_number.upper()))


# ---- greeting and language -----------------------------------------------------------------------------------------------
def test_call_opens_in_tamil_by_default_and_names_the_assistant_and_other_languages(c):
    first = Call(c, "store-a").first
    assert first["language"] == "ta" and "Scout" in first["say"] and "Summit Trail Co" in first["say"]
    assert "Co.." not in first["say"] and "Co.-" not in first["say"]
    assert "You can also speak English" in first["say"] and "हिंदी" in first["say"]


@pytest.mark.parametrize("language,word", [("en", "Thanks for calling"), ("hi", "कॉल करने के लिए धन्यवाद")])
def test_call_can_open_in_a_chosen_language(c, language, word):
    first = Call(c, "store-b", language).first
    assert first["language"] == language and word in first["say"] and "Maple" in first["say"]


def test_start_rejects_unknown_languages_and_fields(c):
    assert c.post("/api/phone/simulator/store-a/calls", json={"language": "fr"}).status_code == 422
    assert c.post("/api/phone/simulator/store-a/calls", json={"agent": True}).status_code == 422


def test_caller_language_is_followed_and_can_be_switched_mid_question(c):
    call = Call(c, "store-a", "en")
    ta = call.say("எனது ஆர்டர் எங்கே?")
    assert ta["language"] == "ta" and "ஆர்டர் எண்ணை" in ta["say"]
    en = call.say("English")
    assert en["language"] == "en" and "continue in English" in en["say"] and "order number" in en["say"]


# ---- order status --------------------------------------------------------------------------------------------------------
def test_order_status_is_spoken_with_a_readable_date_and_offers_care(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h, deliver=False)
    db_exec(c.app.state.settings, "store-a", "UPDATE orders SET estimated_delivery = DATE '2030-01-04' WHERE order_number = %s", [o["number"]])
    call = Call(c, "store-a", "en")
    assert "order number" in call.say("Where is my order?")["say"]
    assert "six-digit shipping PIN code" in call.say(o["number"])["say"]
    out = call.say(digits=PIN)
    assert f"Order {o['number']} is being prepared" in out["say"] and "Friday, 4 January" in out["say"] and "2030-01-04" not in out["say"]
    assert "complaint" in out["say"] and "anything else" in out["say"]


@pytest.mark.parametrize("pin", ["६२५५२१", "௬௨௫௫௨௧", "six two five five two one", "ஆறு இரண்டு ஐந்து ஐந்து இரண்டு ஒன்று",
                                 "छह दो पाँच पाँच दो एक", "it's 6 2 5 5 2 1"])
def test_pin_is_understood_in_any_script_or_as_words(c, pin):
    h, _ = new_customer(c, "store-b")
    o = order(c, "store-b", h, deliver=False)
    call = Call(c, "store-b", "en")
    call.say(f"where is my order {o['number']}")
    assert o["number"] in call.say(pin)["say"]


def test_spelled_order_number_is_understood(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h, deliver=False)
    digits = " ".join("zero one two three four five six seven eight nine".split()[int(d)] for d in o["number"][3:])
    call = Call(c, "store-a", "en")
    call.say("I want to check my order")
    assert "PIN code" in call.say(f"S A {digits}")["say"]
    assert o["number"] in call.say(digits=PIN)["say"]


# ---- the caller is never stuck, and never charged a guess for silence or a sentence -------------------------------------
def test_silence_is_not_a_wrong_guess_and_ends_the_call_politely(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h, deliver=False)
    call = Call(c, "store-a", "en")
    call.say(f"track order {o['number']}")
    first = call.say("")
    assert "didn't hear anything" in first["say"] and "PIN code" in first["say"] and not first["hang_up"]
    call.say(digits="")
    assert guard_failures(c, "store-a", o["number"]) == 0
    last = call.say("")
    assert last["hang_up"] is True and "can't hear you" in last["say"]


def test_a_question_instead_of_the_pin_is_answered_and_not_counted_as_a_guess(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h, deliver=False)
    call = Call(c, "store-a", "en")
    call.say(f"track order {o['number']}")
    out = call.say("do you have a backpack under 3000 rupees")
    assert "don't match" not in out["say"] and "Daypack" in out["say"]
    assert guard_failures(c, "store-a", o["number"]) == 0


def test_asking_for_a_person_mid_verification_is_not_ignored(c):
    call = Call(c, "store-a", "en")
    call.say("where is my order")
    out = call.say("operator")
    assert "can't transfer you" in out["say"] and "order number" in out["say"]


def test_cancel_returns_to_the_menu(c):
    call = Call(c, "store-b", "en")
    call.say("I want to return something")
    out = call.say("cancel")
    assert "nothing was recorded" in out["say"] and "How can I help" in out["say"]
    assert "₹" in call.say("how much is shipping")["say"]


def test_yes_to_anything_else_asks_what(c):
    assert "How can I help" in Call(c, "store-a", "en").say("yes")["say"]


@pytest.mark.parametrize("bye", ["நன்றி", "धन्यवाद", "thanks", "no", "that's all, bye"])
def test_thanks_or_no_ends_the_call(c, bye):
    out = Call(c, "store-a", "en").say(bye)
    assert out["hang_up"] is True


# ---- a request for a person is recorded, never "transferred" --------------------------------------------------------------
def test_asking_for_a_person_never_claims_a_transfer(c):
    call = Call(c, "store-a", "en")
    out = call.say("Can I talk to a real person?")
    assert out["transfer_to_agent"] is False and not out["hang_up"]
    assert "can't transfer you to a person" in out["say"] and "transfer you to a member" not in out["say"]
    contact = call.say("no order")
    assert "help@summittrail.example.com" in contact["say"] and "Support hours" in contact["say"]


def test_team_request_is_recorded_for_the_verified_order_and_staff_see_it(c):
    h, _ = new_customer(c, "store-b")
    o = order(c, "store-b", h)
    call = Call(c, "store-b", "hi")
    call.say("मुझे किसी इंसान से बात करनी है")
    call.verify(o["number"])
    assert "अपने शब्दों में" in call.say(digits="1")["say"]      # reason: 1 = order problem; next, the description
    review = call.say("मेरा ऑर्डर बहुत देर से आया और किसी ने ईमेल का जवाब नहीं दिया")
    assert "1 दबाएँ" in review["say"]
    done = call.say(digits="1")
    assert "हो गया" in done["say"] and "लाइव बातचीत नहीं" in done["say"]
    mine = requests_of(c, "store-b", h)
    assert len(mine) == 1 and mine[0]["kind"] == "escalation" and mine[0]["order_number"] == o["number"]
    assert mine[0]["reference"] in done["say"] and spelled(mine[0]["reference"]) in done["say"]
    queue = c.get("/api/stores/store-b/staff/care", headers=agent(c, "store-b")).json()
    assert any(r["reference"] == mine[0]["reference"] for r in queue["requests"])


# ---- complaints, returns, simulated refunds -----------------------------------------------------------------------------
def test_complaint_by_phone_end_to_end_in_english(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h, items=["lumen-300-headlamp", "pocketflame-stove"])
    call = Call(c, "store-a", "en")
    start = call.say("One thing in my order arrived broken and it will not switch on at all")
    assert "check one of your orders" in start["say"]
    items = call.verify(o["number"])
    assert "press 1" in items["say"] and "Lumen 300 Headlamp" in items["say"] and "whole order, press 0" in items["say"]
    number = re.search(r"For Lumen 300 Headlamp, press (\d)", items["say"]).group(1)
    review = call.say(f"the {['first', 'second'][int(number) - 1]} one")
    assert "read it back" in review["say"] and "Damaged product" in review["say"] and "will not switch on" in review["say"]
    assert "item Lumen 300 Headlamp" in review["say"]
    assert requests_of(c, "store-a", h) == []          # nothing is saved before the explicit yes
    done = call.say("yes")
    mine = requests_of(c, "store-a", h)
    assert len(mine) == 1 and mine[0]["kind"] == "complaint" and mine[0]["item"]["name"] == "Lumen 300 Headlamp"
    assert f"reference is {mine[0]['reference']}" in done["say"] and "My requests" in done["say"]
    # Calling again about the same item: the open request is named, nothing new is recorded.
    again = Call(c, "store-a", "en")
    again.say("I want to complain, my headlamp is broken")
    dup = again.verify(o["number"])                      # the item named in the first sentence is used
    assert "already have an open request" in dup["say"] and mine[0]["reference"] in dup["say"]
    assert len(requests_of(c, "store-a", h)) == 1


def test_complaint_in_tamil_with_spoken_answers(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h)
    call = Call(c, "store-a")
    call.say("எனக்கு புகார் அளிக்க வேண்டும்")
    out = call.verify(o["number"])
    assert "காரணம்" in out["say"]                        # one item: straight to the reason
    assert "சொந்த வார்த்தைகளில்" in call.say("ஒன்று")["say"]
    review = call.say("பொருள் உடைந்து வந்தது, பெட்டியும் கிழிந்திருந்தது")
    assert "ஆம்" in review["say"]
    done = call.say("ஆம்")
    mine = requests_of(c, "store-a", h)
    assert len(mine) == 1 and mine[0]["reference"] in done["say"] and done["language"] == "ta"


def test_return_by_phone_states_the_policy_window(c):
    h, _ = new_customer(c, "store-b")
    o = order(c, "store-b", h)
    call = Call(c, "store-b", "en")
    call.say("I want to return my order")
    out = call.verify(o["number"])
    assert "30-day policy" in out["say"] and "What is the reason" in out["say"]
    assert "describe" in call.say(digits="5")["say"]    # 5 = other
    call.say("It is not what I expected")
    done = call.say(digits="1")
    mine = requests_of(c, "store-b", h)
    assert len(mine) == 1 and mine[0]["kind"] == "return" and mine[0]["reference"] in done["say"]
    # The order itself is unchanged by a return request.
    assert c.get(f"/api/stores/store-b/orders/{o['number']}", headers=h).json()["order"]["status"] == "delivered"


def test_refund_is_simulated_and_said_so(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h)
    call = Call(c, "store-a", "en")
    call.say("I need a refund, I was charged twice for this order")
    review = call.verify(o["number"])
    assert "Charged incorrectly" in review["say"] and "simulated" in review["say"]
    done = call.say("yes")
    assert "simulated" in done["say"] and "no real money" in done["say"]
    assert requests_of(c, "store-a", h)[0]["kind"] == "refund"


def test_ineligible_return_offers_a_complaint_which_works_by_key_press(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h, deliver=False)            # paid, not delivered: no return yet
    call = Call(c, "store-a", "en")
    call.say("I want to return my order")
    out = call.verify(o["number"])
    assert "can't record a return request" in out["say"] and "hasn't been delivered" in out["say"] and "press 1" in out["say"]
    nxt = call.say(digits="1")
    assert "reason" in nxt["say"].lower()
    assert requests_of(c, "store-a", h) == []


def test_cancelling_at_the_review_records_nothing(c):
    h, _ = new_customer(c, "store-b")
    o = order(c, "store-b", h)
    call = Call(c, "store-b", "en")
    call.say("I want to complain, the honey jar was cracked and leaking everywhere in the box")
    call.verify(o["number"])
    out = call.say(digits="2")
    assert "nothing was recorded" in out["say"] and requests_of(c, "store-b", h) == []


def test_secret_codes_in_the_description_are_never_stored(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h)
    call = Call(c, "store-a", "en")
    call.say("I want to make a complaint")
    call.verify(o["number"])
    call.say(digits="6")                                  # 6 = other
    warn = call.say("my card number is 4111 1111 1111 1111")
    assert "card numbers" in warn["say"] and "4111" not in warn["say"]
    assert "read it back" in call.say("the box was open when it arrived")["say"]


# ---- privacy: only the verified order -------------------------------------------------------------------------------------
def test_request_status_covers_only_the_verified_order(c):
    h, _ = new_customer(c, "store-a")
    first = order(c, "store-a", h)
    second = order(c, "store-a", h)
    for o in (first, second):
        call = Call(c, "store-a", "en")
        call.say("I want to make a complaint, the item is of poor quality and stitching came apart")
        call.verify(o["number"])
        call.say("yes")
    refs = {r["order_number"]: r["reference"] for r in requests_of(c, "store-a", h)}
    call = Call(c, "store-a", "en")
    call.say("what is the status of my complaint")
    out = call.verify(first["number"])
    assert refs[first["number"]] in out["say"] and refs[second["number"]] not in out["say"]
    # Asking by the other order's reference gives the same answer as an unknown one.
    other = call.say(f"what is the status of {refs[second['number']]}")
    assert "PIN code" in other["say"] or "no customer-care requests" in other["say"]


def test_a_store_b_order_cannot_be_used_on_a_store_a_call(c):
    h, _ = new_customer(c, "store-b")
    o = order(c, "store-b", h)
    call = Call(c, "store-a", "en")
    call.say(f"I want to complain about order {o['number']}")
    out = call.say(digits=PIN)
    assert "don't match" in out["say"] and requests_of(c, "store-b", h) == []


def test_seeded_demo_order_still_verifies_with_its_us_zip(c):
    call = Call(c, "store-a", "en")
    out = call.verify("SA-10001", "80302")
    assert "SA-10001 is shipped" in out["say"]
    alex = login(c, "store-a", ALEX, PW_A)
    assert isinstance(requests_of(c, "store-a", alex), list)


# ---- small pieces -----------------------------------------------------------------------------------------------------------
def test_spoken_helpers():
    from datetime import date
    assert spelled("SA-CMP-00012") == "S A, C M P, 0 0 0 1 2"
    assert spoken_date("en", date(2026, 11, 13)) == "Friday, 13 November"
    assert spoken_date("ta", "2026-11-13") == "13 நவம்பர்" and spoken_date("hi", "2026-11-13") == "13 नवंबर"
    assert ps.code_digits("it's eight zero three zero two") == "80302"
    assert ps.code_digits("a backpack under 3000 rupees") == ""
    assert ps.ascii_digits("६०६१४") == "60614"

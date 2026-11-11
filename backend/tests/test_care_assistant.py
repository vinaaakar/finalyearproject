"""Scout and Maple register customer-care requests by conversation (India configuration, both stores): Tamil / English /
Hindi recognition, follow-up questions for missing information, context across language switches, explicit confirmation
before anything is created, references read back only from the database, status answers from the customer's own
records, honest refusals, and store isolation. Uses the real chat endpoint (deterministic templates, no language model)."""

from __future__ import annotations

import pytest

from .conftest import db_exec, new_customer
from .test_care_requests import agent, c, demo_list, order  # noqa: F401  (fixtures and the order helper)
from .test_multilingual_acceptance import reply_script


class Chat:
    """A conversation as the chat widget runs it: history + the server's care_draft sent back with every message."""

    def __init__(self, client, store, headers=None, lang="ta"):
        self.c, self.store, self.h, self.lang = client, store, headers or {}, lang
        self.history, self.draft = [], None

    def say(self, message):
        body = {"message": message, "history": self.history[-8:], "channel": "web_chat", "conversation_language": self.lang}
        if self.draft is not None:
            body["care_draft"] = self.draft
        r = self.c.post(f"/api/stores/{self.store}/chat", json=body, headers=self.h)
        assert r.status_code == 200, r.text
        j = r.json()
        self.history += [{"role": "user", "content": message}, {"role": "assistant", "content": j["reply"]}]
        self.draft, self.lang = j.get("care_draft"), j["language"]
        return j


def requests_of(c, store, h):
    return c.get(f"/api/stores/{store}/care/requests", headers=h).json()["requests"]


@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_english_complaint_full_conversation_reference_comes_from_the_database(c, store):
    from .test_care_requests import SLUGS
    h, _ = new_customer(c, store)
    o = order(c, store, h, items=SLUGS[store])
    chat = Chat(c, store, h, "en")
    j = chat.say("I received a damaged product.")
    assert j["language"] == "en" and chat.draft["kind"] == "complaint" and chat.draft["category"] == "damaged"
    assert o["number"] in j["reply"] and "Which order" in j["reply"]                          # asks, doesn't guess
    j = chat.say(o["number"])
    assert "Which item" in j["reply"] and chat.draft["step"] == "item"
    j = chat.say("2")
    assert "describe" in j["reply"] and chat.draft["item_id"] == o["items"][1]
    j = chat.say("The handle snapped off when I opened the box.")
    assert "Please check before I submit" in j["reply"] and "The handle snapped off" in j["reply"] and "care_review" in j["intents"]
    assert requests_of(c, store, h) == []                                                     # nothing before an explicit yes
    assert [a["text"] for a in j["actions"]] == ["yes", "cancel"]
    j = chat.say("yes")
    mine = requests_of(c, store, h)
    assert len(mine) == 1 and j["care_reference"] == mine[0]["reference"] and mine[0]["reference"] in j["reply"]
    assert mine[0]["kind"] == "complaint" and mine[0]["category"] == "damaged" and mine[0]["item"]["id"] == o["items"][1]
    assert chat.draft is None and {"type": "link", "to": f"/support/requests/{mine[0]['reference']}",
                                   "label": f"View {mine[0]['reference']}"} in j["actions"]
    j = chat.say("yes")                                                                        # a repeated yes creates nothing
    assert len(requests_of(c, store, h)) == 1 and j.get("care_reference") is None


def test_tamil_wrong_item_complaint_switches_to_hindi_and_english_keeping_the_draft(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h)
    chat = Chat(c, "store-a", h, "ta")
    j = chat.say("எனக்கு தவறான பொருள் வந்துள்ளது.")
    assert j["language"] == "ta" and reply_script(j["reply"]) == "ta" and chat.draft["category"] == "wrong_item"
    assert o["number"] in j["reply"]
    j = chat.say(o["number"])                                       # one item: chosen automatically; asks for the details
    assert chat.draft["order"] == o["number"] and chat.draft["step"] == "description" and reply_script(j["reply"]) == "ta"
    j = chat.say("मुझे हेडलैम्प की जगह स्टोव मिला")                       # the details, in Hindi
    assert j["language"] == "hi" and reply_script(j["reply"]) == "hi" and "स्टोव" in j["reply"] and chat.draft["step"] == "confirm"
    j = chat.say("Yes, please submit it")                            # confirmed in English
    mine = requests_of(c, "store-a", h)
    assert j["language"] == "en" and len(mine) == 1 and mine[0]["reference"] in j["reply"] and mine[0]["category"] == "wrong_item"
    assert mine[0]["description"] == "मुझे हेडलैम्प की जगह स्टोव मिला"


def test_hindi_return_request_states_the_policy_window_and_submits_after_haan(c):
    h, _ = new_customer(c, "store-b")
    o = order(c, "store-b", h)
    chat = Chat(c, "store-b", h, "ta")
    j = chat.say("मुझे अपना सामान वापस करना है।")
    assert j["language"] == "hi" and chat.draft["kind"] == "return" and chat.draft["order"] == o["number"]
    assert "30 दिन" in j["reply"] and "कारण" in j["reply"]                                     # Bloom & Brew's own 30-day window
    j = chat.say("4")                                                                           # "No longer needed"
    assert chat.draft["category"] == "no_longer_needed" and chat.draft["step"] == "description"
    j = chat.say("मुझे अब इसकी ज़रूरत नहीं है, पैकेट बंद है")
    assert chat.draft["step"] == "confirm"
    j = chat.say("हाँ")
    mine = requests_of(c, "store-b", h)
    assert len(mine) == 1 and mine[0]["reference"].startswith("BB-RET-") and mine[0]["reference"] in j["reply"]
    assert reply_script(j["reply"]) == "hi"


def test_refund_request_is_simulated_and_escalation_never_claims_a_live_agent(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h)
    chat = Chat(c, "store-a", h, "en")
    j = chat.say("I want to request a refund.")
    assert chat.draft["kind"] == "refund" and chat.draft["order"] == o["number"] and "reason" in j["reply"]
    chat.say("Damaged product")
    chat.say("It arrived broken and I would like my money back.")
    j = chat.draft and chat.say("yes")
    assert "no real money is transferred" in j["reply"] and "RFD" in j["care_reference"]
    chat2 = Chat(c, "store-a", h, "en")
    j = chat2.say("Can I speak to customer support?")
    assert chat2.draft["kind"] == "escalation" and "Which order" in j["reply"] and "no order" in j["reply"]
    chat2.say("no order")
    j = chat2.say("Order problem")
    j = chat2.say("I need someone to check my delivery address please")
    assert "no one is live in this chat" in j["reply"]
    j = chat2.say("yes")
    assert "ESC" in j["care_reference"] and "recorded for staff review" in j["reply"] and "not a live conversation" in j["reply"]
    for bad in ("is online", "is connecting", "transferring you", "will call you"):
        assert bad not in j["reply"]


def test_tamil_human_help_request(c):
    h, _ = new_customer(c, "store-b")
    chat = Chat(c, "store-b", h, "en")
    j = chat.say("எனக்கு மனித உதவி வேண்டும்.")
    assert j["language"] == "ta" and chat.draft["kind"] == "escalation" and reply_script(j["reply"]) == "ta"


def test_cancel_and_missing_information_never_submit(c):
    h, _ = new_customer(c, "store-a")
    order(c, "store-a", h)
    chat = Chat(c, "store-a", h, "en")
    chat.say("My item arrived broken")
    chat.say("1")
    j = chat.say("cancel")
    assert "nothing was submitted" in j["reply"] and chat.draft is None and requests_of(c, "store-a", h) == []
    chat = Chat(c, "store-a", h, "en")
    chat.say("I have a complaint")
    chat.say("1")
    j = chat.say("What tents do you have?")                      # an unrelated question mid-request: answered, draft kept
    assert "Tent" in j["reply"] and chat.draft is not None and chat.draft["kind"] == "complaint"
    assert requests_of(c, "store-a", h) == []


def test_ineligible_return_and_duplicate_are_reported_honestly(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h, deliver=False)                    # paid, not delivered
    chat = Chat(c, "store-a", h, "en")
    j = chat.say("I want to return my order")
    assert "hasn't been delivered" in j["reply"] and chat.draft is None and requests_of(c, "store-a", h) == []
    assert {a["text"] for a in j["actions"]} == {"I want to report a problem", "I need human help"}
    # duplicate: an open complaint for the same order item already exists
    c.post("/api/stores/store-a/care/requests", headers={**h, "Idempotency-Key": "dup-chat-test-000001"},
           json={"kind": "complaint", "category": "damaged", "description": "Broken.", "order_number": o["number"], "item_id": o["items"][0]})
    chat = Chat(c, "store-a", h, "en")
    chat.say("My product is damaged")
    chat.say(o["number"])
    chat.say("It is cracked on the side.")
    j = chat.say("yes")
    assert "already have an open request" in j["reply"] and "Nothing new was submitted" in j["reply"] and j["care_reference"] is None
    assert len(requests_of(c, "store-a", h)) == 1


def test_status_questions_in_three_languages_use_only_the_customers_records(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h)
    ref = c.post("/api/stores/store-a/care/requests", headers={**h, "Idempotency-Key": "status-chat-test-0001"},
                 json={"kind": "complaint", "category": "quality", "description": "Weak beam.", "order_number": o["number"]}).json()["request"]["reference"]
    a = agent(c, "store-a")
    c.post(f"/api/stores/store-a/staff/care/{ref}/status", headers=a, json={"status": "under_review", "expected_status": "open"})
    c.post(f"/api/stores/store-a/staff/care/{ref}/messages", headers=a, json={"body": "We are checking this batch."})
    chat = Chat(c, "store-a", h, "en")
    j = chat.say("What is the status of my complaint?")
    assert ref in j["reply"] and "Under review" in j["reply"] and "We are checking this batch." in j["reply"]
    j = chat.say("எனது புகார் நிலை என்ன?")
    assert j["language"] == "ta" and ref in j["reply"] and "பரிசீலனையில்" in j["reply"]
    j = chat.say("मेरी शिकायत की स्थिति क्या है?")
    assert j["language"] == "hi" and ref in j["reply"] and "समीक्षा में" in j["reply"]
    j = chat.say("Show my return request status.")
    assert "don't have any" in j["reply"] or ref not in j["reply"]
    # another customer, and the other store, never see it
    h2, _ = new_customer(c, "store-a")
    assert "couldn't find" in Chat(c, "store-a", h2, "en").say(f"What is the status of {ref}?")["reply"]
    hb, _ = new_customer(c, "store-b")
    assert "couldn't find" in Chat(c, "store-b", hb, "en").say(f"Status of {ref}?")["reply"]


def test_signed_out_and_tampered_drafts_are_refused(c, settings):
    j = Chat(c, "store-a", None, "en").say("I received a damaged product.")
    assert j["requires_login"] and "sign in" in j["reply"]
    victim, _ = new_customer(c, "store-a")
    o = order(c, "store-a", victim)
    h, _ = new_customer(c, "store-a")
    chat = Chat(c, "store-a", h, "en")
    chat.draft = {"kind": "complaint", "step": "confirm", "order": o["number"], "category": "damaged",
                  "description": "not mine", "key": "chat_aaaaaaaaaaaaaaaaaaaa"}
    j = chat.say("yes")
    assert "wasn't found on your account" in j["reply"] or "Which order" in j["reply"]
    assert requests_of(c, "store-a", h) == [] and requests_of(c, "store-a", victim) == []
    before = db_exec(settings, "store-a", "SELECT count(*) FROM care_requests")[0][0]
    chat.draft = {"kind": "refund", "step": "confirm", "order": None, "category": "nonsense", "description": "x" * 5000}
    chat.say("yes")
    assert db_exec(settings, "store-a", "SELECT count(*) FROM care_requests")[0][0] == before

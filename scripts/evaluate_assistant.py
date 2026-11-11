#!/usr/bin/env python3
"""Repeatable evaluation of Scout and Maple (India configuration) on the ISOLATED *_test databases.

Measures, on fixed datasets written below (sample sizes are reported with every number):
  1. language identification of typed messages (ta / en / hi)
  2. context retention across a language change (follow-up about "it" in another language)
  3. product recommendation accuracy (the first product shown is one of the expected products of this store)
  4. exact INR price answers (every product, in all three languages)
  5. customer-care task completion by conversation (4 request types x 3 languages x 2 stores), then the staff
     lifecycle to its final status, and that refund requests create no payment rows
  6. find -> compare -> add to cart (by conversation) -> checkout -> order status (by conversation), 3 languages x 2 stores
  7. latency: every chat call above (median / p90, by reply source); with --llm the local Ollama model on English policy
     prompts; with --voice the voice turn (local whisper.cpp transcription + chat) on synthetic macOS-voice audio

Safety: refuses to run unless both database URLs name *_test databases whose applied migrations match
backend/migrations. Everything it writes is synthetic (new test customers, carts, orders, care requests) in the test
databases. The demonstration INR price list and the stock levels it sets are removed / restored at the end. Never
touches the development databases, never migrates, never downloads anything.

Usage: backend/.venv/bin/python scripts/evaluate_assistant.py [--llm] [--voice] [--json out.json]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

STORES = ("store-a", "store-b")
AGENTS = {"store-a": "agent@summittrail.example.com", "store-b": "agent@bloomandbrew.example.com"}
OUT_OF_STOCK = {"basecamp-4p-tent", "house-blend-beans"}           # as in the development catalogue
ADDRESS = {"full_name": "Eval Shopper", "line1": "12 Kambam Main Road", "city": "Cumbum", "region": "TN",
           "postal_code": "625521", "country": "IN", "phone": "+91 98765 43210"}

# ---- datasets (fixed; do not tune them to the results) -------------------------------------------------------------
LANGUAGE_ID = [
    ("ta", "உங்களிடம் இரண்டு பேர் தங்கும் கூடாரம் இருக்கிறதா?"), ("ta", "திருப்பி அனுப்பும் கொள்கை என்ன?"),
    ("ta", "என் ஆர்டர் எங்கே இருக்கிறது?"), ("ta", "ஷிப்பிங் கட்டணம் எவ்வளவு?"), ("ta", "எனக்கு ஒரு நல்ல hiking bag வேண்டும்"),
    ("ta", "மிகவும் மலிவான காபி எது?"), ("ta", "இதன் விலை என்ன?"), ("ta", "எனக்கு மனித உதவி வேண்டும்"),
    ("en", "Do you have a two person tent?"), ("en", "What is your return policy?"), ("en", "Where is my order?"),
    ("en", "How much is shipping?"), ("en", "Show me the best one under 5000 rupees."), ("en", "I want to request a refund."),
    ("en", "Compare the French press and the pour-over dripper"), ("en", "What are your support hours?"),
    ("hi", "क्या आपके पास दो लोगों का टेंट है?"), ("hi", "आपकी वापसी नीति क्या है?"), ("hi", "मेरा ऑर्डर कहाँ है?"),
    ("hi", "शिपिंग कितनी है?"), ("hi", "मुझे इसकी कीमत बताइए।"), ("hi", "सबसे सस्ती चाय कौन सी है?"),
    ("hi", "मुझे अपना सामान वापस करना है।"), ("hi", "मुझे कॉफ़ी बीन्स चाहिए"),
]
RECOMMEND = [
    ("store-a", "en", "Do you have a tent for two people?", {"ridgeline-2p-tent"}),
    ("store-a", "en", "I need a sleeping bag for cold nights", {"alpine-20f-sleeping-bag"}),
    ("store-a", "en", "Show me a backpack under ₹5,000", {"daytrip-22l-daypack"}),
    ("store-a", "en", "I need a headlamp", {"lumen-300-headlamp"}),
    ("store-a", "en", "What's the cheapest sleeping bag?", {"alpine-20f-sleeping-bag"}),
    ("store-a", "en", "Rain jacket please", {"stormshell-rain-jacket"}),
    ("store-a", "ta", "உங்களிடம் இரண்டு பேர் தங்கும் கூடாரம் இருக்கிறதா?", {"ridgeline-2p-tent"}),
    ("store-a", "ta", "எனக்கு ஒரு ஹெட்லேம்ப் வேண்டும்", {"lumen-300-headlamp"}),
    ("store-a", "ta", "மிகவும் மலிவான தூங்கும் பை எது?", {"alpine-20f-sleeping-bag"}),
    ("store-a", "hi", "क्या आपके पास दो लोगों का टेंट है?", {"ridgeline-2p-tent"}),
    ("store-a", "hi", "मुझे बारिश की जैकेट चाहिए", {"stormshell-rain-jacket"}),
    ("store-a", "hi", "सबसे सस्ता स्लीपिंग बैग कौन सा है?", {"alpine-20f-sleeping-bag"}),
    ("store-b", "en", "Which coffee beans do you have?", {"ethiopia-yirgacheffe-beans", "house-blend-beans"}),
    ("store-b", "en", "I need a grinder", {"precision-burr-grinder"}),
    ("store-b", "en", "Show me tea under ₹500", {"sencha-green-tea", "spiced-chai-blend"}),
    ("store-b", "en", "What's the cheapest tea?", {"spiced-chai-blend"}),
    ("store-b", "en", "I want a French press", {"classic-french-press"}),
    ("store-b", "ta", "உங்களிடம் என்ன காபி பீன்ஸ் உள்ளன?", {"ethiopia-yirgacheffe-beans", "house-blend-beans"}),
    ("store-b", "ta", "எனக்கு ஒரு கெட்டில் வேண்டும்", {"gooseneck-kettle"}),
    ("store-b", "ta", "மிகவும் மலிவான தேநீர் எது?", {"spiced-chai-blend"}),
    ("store-b", "hi", "आपके पास कौन-सी कॉफ़ी बीन्स हैं?", {"ethiopia-yirgacheffe-beans", "house-blend-beans"}),
    ("store-b", "hi", "मुझे शहद चाहिए", {"wildflower-honey"}),
    ("store-b", "hi", "सबसे सस्ती चाय कौन सी है?", {"spiced-chai-blend"}),
]
PRICE_QUESTION = {"en": "How much is the {name}?", "ta": "{name} விலை என்ன?", "hi": "{name} की कीमत क्या है?"}
# (store, [(lang, message)], expected language of the last reply, expected product, text the last reply must contain)
CONTEXT = [
    ("store-a", [("ta", "இரண்டு பேருக்கு ₹10,000க்குள் கூடாரம் இருக்கிறதா?"), ("hi", "इसका वज़न कितना है?")], "hi", "ridgeline-2p-tent", "1.9 kg"),
    ("store-a", [("en", "Tell me about the Lumen 300 headlamp"), ("ta", "இதன் விலை என்ன?")], "ta", "lumen-300-headlamp", "₹899.00"),
    ("store-a", [("hi", "मुझे बारिश की जैकेट चाहिए"), ("en", "Add it to my cart")], "en", "stormshell-rain-jacket", None),
    ("store-b", [("en", "Tell me about the gooseneck kettle"), ("hi", "इसकी कीमत क्या है?")], "hi", "gooseneck-kettle", "₹3,299.00"),
    ("store-b", [("ta", "எனக்கு ஒரு கிரைண்டர் வேண்டும்"), ("en", "How much is it?")], "en", "precision-burr-grinder", "₹7,499.00"),
    ("store-b", [("hi", "मुझे शहद चाहिए"), ("ta", "இதை கார்ட்டில் சேர்")], "ta", "wildflower-honey", None),
]
CARE_START = {
    "complaint": {"en": "I received a damaged product.", "ta": "எனக்கு சேதமடைந்த பொருள் வந்தது.", "hi": "मुझे टूटा हुआ सामान मिला है।"},
    "return": {"en": "I want to return my order.", "ta": "என் ஆர்டரைத் திருப்பி அனுப்ப வேண்டும்.", "hi": "मुझे अपना सामान वापस करना है।"},
    "refund": {"en": "I want to request a refund.", "ta": "எனக்கு பணத்தைத் திருப்பித் தர வேண்டும்.", "hi": "मुझे रिफ़ंड चाहिए।"},
    "escalation": {"en": "Can I speak to customer support?", "ta": "எனக்கு மனித உதவி வேண்டும்.", "hi": "मुझे किसी इंसान से बात करनी है।"},
}
CARE_DETAILS = {"en": "The item arrived cracked and I would like help with it.", "ta": "பொருள் உடைந்த நிலையில் வந்தது, உதவி வேண்டும்.",
                "hi": "सामान टूटा हुआ आया है, कृपया मदद करें।"}
YES = {"en": "yes", "ta": "ஆம்", "hi": "हाँ"}
STAFF_PATH = {
    "complaint": [("open", "under_review"), ("under_review", "resolved")],
    "return": [("requested", "under_review"), ("under_review", "approved"), ("approved", "received"), ("received", "inspected"),
               ("inspected", "completed")],
    "refund": [("requested", "under_review"), ("under_review", "approved"), ("approved", "simulated_completed")],
    "escalation": [("assigned", "in_progress"), ("in_progress", "resolved")],
}
JOURNEY = {
    "store-a": {"find": {"en": "Do you have a 2 person tent?", "ta": "உங்களிடம் இரண்டு பேர் தங்கும் கூடாரம் இருக்கிறதா?",
                         "hi": "क्या आपके पास दो लोगों का टेंट है?"},
                "compare": {"en": "Compare the Ridgeline 2-Person Tent and the Lumen 300 Headlamp",
                            "ta": "Ridgeline 2-Person Tent மற்றும் Lumen 300 Headlamp ஒப்பிடு",
                            "hi": "Ridgeline 2-Person Tent और Lumen 300 Headlamp की तुलना करें"},
                "cart": {"en": "Add the Lumen 300 Headlamp to my cart", "ta": "Lumen 300 Headlamp-ஐ கார்ட்டில் சேர்",
                         "hi": "Lumen 300 Headlamp कार्ट में डालो"}, "slug": "lumen-300-headlamp"},
    "store-b": {"find": {"en": "Which coffee beans do you have?", "ta": "உங்களிடம் என்ன காபி பீன்ஸ் உள்ளன?",
                         "hi": "आपके पास कौन-सी कॉफ़ी बीन्स हैं?"},
                "compare": {"en": "Compare the Classic French Press and the Ceramic Pour-Over Dripper",
                            "ta": "Classic French Press மற்றும் Ceramic Pour-Over Dripper ஒப்பிடு",
                            "hi": "Classic French Press और Ceramic Pour-Over Dripper की तुलना करें"},
                "cart": {"en": "Add the Wildflower Honey to my cart", "ta": "Wildflower Honey-ஐ கார்ட்டில் சேர்",
                         "hi": "Wildflower Honey कार्ट में डालो"}, "slug": "wildflower-honey"},
}
STATUS_QUESTION = {"en": "Where is my order?", "ta": "என் ஆர்டர் எங்கே இருக்கிறது?", "hi": "मेरा ऑर्डर कहाँ है?"}
LLM_PROMPTS = [("store-a", "How long does delivery take?"), ("store-a", "What is your return policy?"),
               ("store-a", "Is there a warranty on your gear?"), ("store-a", "How can I contact you?"),
               ("store-b", "How much is shipping?"), ("store-b", "Can I return opened coffee?"),
               ("store-b", "Do grinders have a warranty?"), ("store-b", "How long does delivery take?")]
VOICE_TURNS = [("store-a", "ta", "உங்களிடம் இரண்டு பேர் தங்கும் கூடாரம் இருக்கிறதா?"), ("store-a", "en", "Do you have a two person tent?"),
               ("store-a", "hi", "क्या आपके पास दो लोगों का टेंट है?"), ("store-a", "ta", "ஷிப்பிங் கட்டணம் எவ்வளவு?"),
               ("store-a", "en", "What is your return policy?"), ("store-a", "hi", "आपकी वापसी नीति क्या है?"),
               ("store-b", "ta", "திருப்பி அனுப்பும் கொள்கை என்ன?"), ("store-b", "en", "Which coffee beans do you have?"),
               ("store-b", "hi", "मेरा ऑर्डर कहाँ है?"), ("store-b", "ta", "என் ஆர்டர் எங்கே இருக்கிறது?"),
               ("store-b", "en", "How much is shipping?"), ("store-b", "hi", "शिपिंग कितनी है?")]
VOICES = {"ta": "Vani", "en": "Rishi", "hi": "Lekha"}


# ---- helpers --------------------------------------------------------------------------------------------------------
def test_url(url: str) -> str:
    p = urlparse(url)
    return urlunparse(p._replace(path=p.path.rstrip("/") + "_test"))


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return round(s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))], 1) if s else float("nan")


def stats(values: list[float]) -> dict:
    return {"n": len(values), "median_ms": round(statistics.median(values), 1) if values else None, "p90_ms": pct(values, 0.9) if values else None}


class Session:
    def __init__(self, client, timings: list):
        self.c, self.timings = client, timings

    def chat(self, store, message, lang, headers=None, history=None, draft=None):
        body = {"message": message, "history": (history or [])[-8:], "channel": "web_chat", "conversation_language": lang}
        if draft is not None:
            body["care_draft"] = draft
        t = time.perf_counter()
        r = self.c.post(f"/api/stores/{store}/chat", json=body, headers=headers or {})
        ms = (time.perf_counter() - t) * 1000
        assert r.status_code == 200, r.text
        j = r.json()
        self.timings.append({"ms": ms, "source": j["source"], "store": store})
        return j

    def customer(self, store):
        email = f"eval-{uuid.uuid4().hex[:10]}@example.com"
        r = self.c.post(f"/api/stores/{store}/auth/register", json={"email": email, "full_name": "Eval Shopper", "password": "Correct-Horse-42"})
        assert r.status_code == 201, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def staff(self, store):
        from app.seed import AGENT_PASSWORD
        r = self.c.post(f"/api/stores/{store}/auth/login", json={"email": AGENTS[store], "password": AGENT_PASSWORD})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def checkout(self, store, h):
        q = self.c.post(f"/api/stores/{store}/checkout/quote", headers=h, json={"shipping_method": "standard",
                        "destination": {"country": "IN", "region": "TN", "postal_code": "625521"}}).json()["cart"]
        r = self.c.post(f"/api/stores/{store}/checkout", headers={**h, "Idempotency-Key": uuid.uuid4().hex},
                        json={"shipping": ADDRESS, "expected_total_cents": q["total_cents"]})
        assert r.status_code == 201, r.text
        number = r.json()["order"]["order_number"]
        ref = self.c.post(f"/api/stores/{store}/orders/{number}/payments", headers=h).json()["payment"]["reference"]
        self.c.post(f"/api/stores/{store}/payments/sandbox/{ref}/complete", headers=h, json={"outcome": "success"})
        status = self.c.post(f"/api/stores/{store}/orders/{number}/payments/verify", headers=h).json()["order"]["status"]
        return number, status

    def delivered_order(self, store, h, slug):
        self.c.post(f"/api/stores/{store}/cart/items", json={"slug": slug, "quantity": 1}, headers=h)
        number, _ = self.checkout(store, h)
        a = self.staff(store)
        self.c.post(f"/api/stores/{store}/staff/orders/{number}/ship", headers=a,
                    json={"expected_status": "processing", "carrier": "DemoPost", "tracking_number": "TRK12345"})
        self.c.post(f"/api/stores/{store}/staff/orders/{number}/deliver", headers=a, json={"expected_status": "shipped"})
        return number


# ---- evaluations ----------------------------------------------------------------------------------------------------
def eval_language(s: Session) -> dict:
    rows = []
    for i, (lang, msg) in enumerate(LANGUAGE_ID):
        store = STORES[i % 2]
        got = s.chat(store, msg, "ta")["language"]           # new conversation (Tamil default)
        rows.append({"expected": lang, "got": got, "message": msg, "ok": got == lang})
    return {"n": len(rows), "correct": sum(r["ok"] for r in rows),
            "by_language": {l: f"{sum(r['ok'] for r in rows if r['expected'] == l)}/{sum(r['expected'] == l for r in rows)}" for l in ("ta", "en", "hi")},
            "errors": [r for r in rows if not r["ok"]]}


def eval_recommend(s: Session, catalogue: dict) -> dict:
    rows = []
    for store, lang, msg, expected in RECOMMEND:
        j = s.chat(store, msg, lang)
        slugs = [p["slug"] for p in j["products"]]
        ok = bool(slugs) and slugs[0] in expected and all(x in catalogue[store] for x in slugs)
        rows.append({"store": store, "lang": lang, "message": msg, "first": slugs[0] if slugs else None, "ok": ok})
    return {"n": len(rows), "correct": sum(r["ok"] for r in rows), "errors": [r for r in rows if not r["ok"]]}


def eval_prices(s: Session, prices: dict) -> dict:
    from app.markets import format_money as format_amount
    rows = []
    for store in STORES:
        for slug, (name, minor) in prices[store].items():
            want = format_amount(minor, "INR")
            for lang, q in PRICE_QUESTION.items():
                j = s.chat(store, q.format(name=name), lang)
                rows.append({"store": store, "lang": lang, "product": slug, "expected": want, "ok": want in j["reply"],
                             "reply": j["reply"][:160]})
    return {"n": len(rows), "correct": sum(r["ok"] for r in rows),
            "by_language": {l: f"{sum(r['ok'] for r in rows if r['lang'] == l)}/{sum(r['lang'] == l for r in rows)}" for l in PRICE_QUESTION},
            "errors": [r for r in rows if not r["ok"]]}


def eval_context(s: Session) -> dict:
    rows = []
    for store, turns, want_lang, slug, text in CONTEXT:
        h = s.customer(store)
        history, j = [], None
        for lang, msg in turns:
            j = s.chat(store, msg, lang, headers=h, history=history)
            history += [{"role": "user", "content": msg}, {"role": "assistant", "content": j["reply"]}]
        named = [p["slug"] for p in j["products"]] + [a.get("slug") for a in j["actions"]]
        ok = j["language"] == want_lang and slug in named and (text is None or text in j["reply"])
        rows.append({"store": store, "turns": [m for _, m in turns], "language": j["language"], "products": named, "ok": ok,
                     "reply": j["reply"][:200]})
    return {"n": len(rows), "correct": sum(r["ok"] for r in rows), "errors": [r for r in rows if not r["ok"]]}


def eval_care(s: Session, settings) -> dict:
    import psycopg
    rows = []
    pay_before = {st: _count(settings, st, "SELECT count(*) FROM payments") for st in STORES}
    for store in STORES:
        slug = "lumen-300-headlamp" if store == "store-a" else "wildflower-honey"
        a = s.staff(store)
        for kind, starts in CARE_START.items():
            for lang, start in starts.items():
                h = s.customer(store)
                number = s.delivered_order(store, h, slug)
                draft, j, history, ref, steps = None, s.chat(store, start, lang, headers=h), [], None, []
                for _ in range(8):
                    history += [{"role": "assistant", "content": j["reply"]}]
                    draft, ref = j.get("care_draft"), j.get("care_reference")
                    if ref or not draft:
                        break
                    step = draft.get("step")
                    steps.append(step)
                    answer = {"order": number, "item": "1", "category": "1", "description": CARE_DETAILS[lang], "confirm": YES[lang]}.get(step)
                    if answer is None:
                        break
                    j = s.chat(store, answer, lang, headers=h, history=history, draft=draft)
                created = s.c.get(f"/api/stores/{store}/care/requests", headers=h).json()["requests"]
                registered = bool(ref) and len(created) == 1 and created[0]["reference"] == ref and created[0]["kind"] == kind
                lifecycle = False
                if registered:
                    if kind == "escalation":
                        agents = s.c.get(f"/api/stores/{store}/staff/care/agents", headers=a).json()["agents"]
                        s.c.post(f"/api/stores/{store}/staff/care/{ref}/assign", headers=a, json={"assignee_id": agents[0]["id"]})
                        s.c.post(f"/api/stores/{store}/staff/care/{ref}/messages", headers=a, json={"body": "We are looking into this (evaluation)."})
                    for frm, to in STAFF_PATH[kind]:
                        s.c.post(f"/api/stores/{store}/staff/care/{ref}/status", headers=a, json={"status": to, "expected_status": frm})
                    final = s.c.get(f"/api/stores/{store}/care/requests/{ref}", headers=h).json()["request"]["status"]
                    lifecycle = final == STAFF_PATH[kind][-1][1]
                rows.append({"store": store, "kind": kind, "lang": lang, "steps": steps, "reference": ref, "registered": registered,
                             "lifecycle_completed": lifecycle, "last_reply": j["reply"][:200]})
    pay_after = {st: _count(settings, st, "SELECT count(*) FROM payments") for st in STORES}
    del psycopg
    n = len(rows)
    return {"n": n, "registered": sum(r["registered"] for r in rows), "lifecycle_completed": sum(r["lifecycle_completed"] for r in rows),
            "by_kind": {k: f"{sum(r['registered'] for r in rows if r['kind'] == k)}/{sum(r['kind'] == k for r in rows)}" for k in CARE_START},
            "by_language": {l: f"{sum(r['registered'] for r in rows if r['lang'] == l)}/{sum(r['lang'] == l for r in rows)}" for l in YES},
            # Payment rows added during the run come only from the orders this evaluation placed (one per conversation).
            "payment_rows_added": {st: pay_after[st] - pay_before[st] for st in STORES}, "orders_placed_per_store": n // 2,
            "failures": [r for r in rows if not (r["registered"] and r["lifecycle_completed"])]}


def eval_journey(s: Session) -> dict:
    rows = []
    for store, script in JOURNEY.items():
        for lang in ("ta", "en", "hi"):
            h, history, steps = s.customer(store), [], {}

            def say(msg):
                j = s.chat(store, msg, lang, headers=h, history=history)
                history.extend([{"role": "user", "content": msg}, {"role": "assistant", "content": j["reply"]}])
                return j
            steps["find"] = bool(say(script["find"][lang])["products"])
            j = say(script["compare"][lang])
            steps["compare"] = "compare" in j["intents"] and len(j["products"]) >= 2
            j = say(script["cart"][lang])
            act = next((a for a in j["actions"] if a.get("type") == "add_to_cart" and a.get("slug") == script["slug"]), None)
            if act:   # what the chat widget does when the customer taps the action
                s.c.post(f"/api/stores/{store}/cart/items", headers=h, json={"slug": act["slug"], "quantity": act.get("quantity", 1)})
            cart = s.c.get(f"/api/stores/{store}/cart", headers=h).json()["cart"]
            steps["cart"] = any(i.get("slug") == script["slug"] for i in cart.get("items", []))
            number, status = s.checkout(store, h) if steps["cart"] else (None, None)
            steps["checkout"] = status == "processing"
            steps["status"] = bool(number) and number in say(STATUS_QUESTION[lang])["reply"]
            rows.append({"store": store, "lang": lang, "steps": steps, "ok": all(steps.values())})
    return {"n": len(rows), "completed": sum(r["ok"] for r in rows),
            "step_success": {k: f"{sum(r['steps'][k] for r in rows)}/{len(rows)}" for k in ("find", "compare", "cart", "checkout", "status")},
            "failures": [r for r in rows if not r["ok"]]}


def eval_llm(base_settings) -> dict:
    from fastapi.testclient import TestClient

    from app.main import create_app
    settings = dataclasses.replace(base_settings, llm_enabled=True)
    rows = []
    with TestClient(create_app(settings)) as c:
        if not c.app.state.llm or not c.app.state.llm.is_available():
            return {"available": False}
        for _ in range(3):
            for store, prompt in LLM_PROMPTS:
                t = time.perf_counter()
                j = c.post(f"/api/stores/{store}/chat", json={"message": prompt, "conversation_language": "en"}).json()
                rows.append({"ms": (time.perf_counter() - t) * 1000, "source": j["source"], "prompt": prompt})
    return {"available": True, "model_attempted": stats([r["ms"] for r in rows]),
            "accepted_from_model": f"{sum(r['source'] == 'llm' for r in rows)}/{len(rows)}",
            "accepted_ms": stats([r["ms"] for r in rows if r["source"] == "llm"]),
            "fallback_to_rules_ms": stats([r["ms"] for r in rows if r["source"] == "rules"]),
            "fell_back_to_rules": sorted({f"{r['prompt']}" for r in rows if r["source"] == "rules"})}


def eval_voice(base_settings) -> dict:
    from fastapi.testclient import TestClient

    from app.main import create_app
    rows = []
    with TestClient(create_app(base_settings, llm=False)) as c, tempfile.TemporaryDirectory() as tmp:
        if not c.app.state.stt.available:
            return {"available": False}
        for i, (store, lang, text) in enumerate(VOICE_TURNS):
            aiff, wav = Path(tmp) / f"{i}.aiff", Path(tmp) / f"{i}.wav"
            subprocess.run(["say", "-v", VOICES[lang], "-o", str(aiff), text], check=True)
            subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)], check=True, capture_output=True)
            t0 = time.perf_counter()
            tr = c.post(f"/api/stores/{store}/speech/transcribe", content=wav.read_bytes(), headers={"Content-Type": "audio/wav"}).json()
            t1 = time.perf_counter()
            body = {"message": tr["text"] or "…", "channel": "web_voice", "conversation_language": "ta"}
            if tr.get("speech_receipt"):
                body["speech_receipt"] = tr["speech_receipt"]
            j = c.post(f"/api/stores/{store}/chat", json=body).json()
            t2 = time.perf_counter()
            rows.append({"store": store, "lang": lang, "heard": tr["text"], "reply_language": j.get("language"),
                         "clarified": bool(j.get("clarification")), "stt_ms": (t1 - t0) * 1000, "chat_ms": (t2 - t1) * 1000,
                         "total_ms": (t2 - t0) * 1000})
    return {"available": True, "n": len(rows), "transcription": stats([r["stt_ms"] for r in rows]), "chat": stats([r["chat_ms"] for r in rows]),
            "voice_turn_total": stats([r["total_ms"] for r in rows]),
            "reply_in_spoken_language": sum(r["reply_language"] == r["lang"] and not r["clarified"] for r in rows),
            "asked_to_clarify": sum(r["clarified"] for r in rows),
            "wrong_language": sum(r["reply_language"] != r["lang"] and not r["clarified"] for r in rows), "rows": rows,
            "note": "excludes browser recording, silence detection and speech synthesis time"}


def _count(settings, store, sql):
    import psycopg
    with psycopg.connect(settings.store_database_urls[store]) as conn:
        return conn.execute(sql).fetchone()[0]


# ---- main -----------------------------------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="also measure the local Ollama model (English policy prompts)")
    ap.add_argument("--voice", action="store_true", help="also measure voice turns (local whisper.cpp + macOS voices)")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    import psycopg
    from fastapi.testclient import TestClient

    from app import demo_prices
    from app.config import PROJECT_ROOT, load_settings
    from app.main import create_app

    base = load_settings()
    urls = {k: test_url(v) for k, v in base.store_database_urls.items()}
    expected = sorted(p.stem for p in (ROOT / "backend" / "migrations").glob("*.sql"))
    for store, url in urls.items():
        if not urlparse(url).path.lstrip("/").endswith("_test"):
            print(f"refusing: {store} is not a *_test database", file=sys.stderr)
            return 2
        with psycopg.connect(url) as conn:
            applied = sorted(r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall())
        if applied != expected:
            print(f"refusing: {store} test database migrations {applied} != {expected}", file=sys.stderr)
            return 3
    settings = dataclasses.replace(
        base, store_database_urls=urls, llm_enabled=False, speech_stt="none", speech_tts="none",
        store_markets={"store-a": "IN", "store-b": "IN"}, checkout_countries=("IN",), shipping_config_dir=PROJECT_ROOT / "config" / "shipping",
        rate_limit_login_per_min=6000, rate_limit_chat_per_min=6000, rate_limit_default_per_min=60000, phone_simulator_enabled=False)
    price_list = demo_prices.load_list()

    def q(store, sql, params=None):
        with psycopg.connect(urls[store]) as conn:
            cur = conn.execute(sql, params or [])
            return cur.fetchall() if cur.description else None

    stock_before = {st: q(st, "SELECT slug, stock_qty FROM products") for st in STORES}
    results: dict = {"date": time.strftime("%Y-%m-%d %H:%M"), "databases": sorted(urlparse(u).path.lstrip("/") for u in urls.values())}
    timings: list = []
    try:
        demo_prices.apply(urls, price_list)
        for st in STORES:
            q(st, "UPDATE products SET stock_qty = CASE WHEN slug = ANY(%s) THEN 0 ELSE 500 END", [list(OUT_OF_STOCK)])
        catalogue = {st: {r[0] for r in q(st, "SELECT slug FROM products")} for st in STORES}
        prices = {st: {r[0]: (r[1], r[2]) for r in q(st, "SELECT p.slug, p.name, pp.price_minor FROM products p JOIN product_prices pp "
                                                          "ON pp.product_id = p.id AND pp.currency = 'INR' ORDER BY p.slug")} for st in STORES}
        with TestClient(create_app(settings, llm=False)) as c:
            s = Session(c, timings)
            results["language_identification"] = eval_language(s)
            results["recommendation"] = eval_recommend(s, catalogue)
            results["inr_price_answers"] = eval_prices(s, prices)
            results["context_across_languages"] = eval_context(s)
            results["customer_care"] = eval_care(s, settings)
            results["find_compare_cart_checkout_status"] = eval_journey(s)
        results["latency_rules_client"] = {"all_chat_calls": stats([t["ms"] for t in timings]),
                                           "rule_based_replies": stats([t["ms"] for t in timings if t["source"] == "rules"])}
        if args.llm:
            results["latency_llm"] = eval_llm(settings)
        if args.voice:
            results["voice"] = eval_voice(dataclasses.replace(settings, speech_stt=base.speech_stt, speech_tts="none"))
    finally:
        for st in STORES:
            q(st, "DELETE FROM product_prices WHERE approved_by = %s", [price_list["approved_by"]])
            q(st, "DELETE FROM outbox WHERE kind = 'email.care_update'")
            for slug, qty in stock_before[st]:
                q(st, "UPDATE products SET stock_qty = %s WHERE slug = %s", [qty, slug])

    def line(name, ok, n):
        print(f"  {name:48} {ok}/{n}  ({100 * ok / n:.1f} %)" if n else f"  {name:48} n/a")
    print(f"Evaluation on {', '.join(results['databases'])} — {results['date']}")
    r = results
    line("language identification (typed)", r["language_identification"]["correct"], r["language_identification"]["n"])
    line("recommendation: first product expected", r["recommendation"]["correct"], r["recommendation"]["n"])
    line("exact INR price in the answer", r["inr_price_answers"]["correct"], r["inr_price_answers"]["n"])
    line("context kept across a language change", r["context_across_languages"]["correct"], r["context_across_languages"]["n"])
    line("care request registered by conversation", r["customer_care"]["registered"], r["customer_care"]["n"])
    line("care request staff lifecycle completed", r["customer_care"]["lifecycle_completed"], r["customer_care"]["n"])
    line("find→compare→cart→checkout→status", r["find_compare_cart_checkout_status"]["completed"], r["find_compare_cart_checkout_status"]["n"])
    lat = r["latency_rules_client"]
    print(f"  chat latency (all, in-process)  n={lat['all_chat_calls']['n']} median {lat['all_chat_calls']['median_ms']} ms, p90 {lat['all_chat_calls']['p90_ms']} ms")
    print(f"  rule-based replies              n={lat['rule_based_replies']['n']} median {lat['rule_based_replies']['median_ms']} ms, p90 {lat['rule_based_replies']['p90_ms']} ms")
    if "latency_llm" in r:
        print(f"  LLM (Ollama) attempts           {json.dumps(r['latency_llm'])}")
    if "voice" in r:
        v = r["voice"]
        print(f"  voice turns                     {json.dumps({k: v[k] for k in v if k != 'rows'}, ensure_ascii=False)}")
    if args.json:
        args.json.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

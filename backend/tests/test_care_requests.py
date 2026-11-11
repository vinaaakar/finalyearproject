"""Customer-care requests API, both stores, India-only configuration (demonstration INR prices and shipping):
complaints, return requests, SIMULATED refund requests and human-help requests — customer creation, validation,
duplicates, ownership, store isolation, staff queues, assignment, notes, messages, decisions and status rules."""

from __future__ import annotations

import ast
import dataclasses
import inspect
import json
import re

import pytest

from app import care_requests, demo_prices
from app.config import PROJECT_ROOT
from app.seed import AGENT_PASSWORD

from .conftest import AGENT_A, AGENT_B, db_exec, idem, login, make_client, new_customer, set_stock

LIST = demo_prices.load_list()
CUMBUM = {"full_name": "Priya Raman", "line1": "12 Kambam Main Road", "city": "Cumbum", "region": "TN",
          "postal_code": "625521", "country": "IN", "phone": "+91 98765 43210"}
SLUGS = {"store-a": ("lumen-300-headlamp", "pocketflame-stove"), "store-b": ("wildflower-honey", "spiced-chai-blend")}
AGENT = {"store-a": AGENT_A, "store-b": AGENT_B}
OTHER = {"store-a": "store-b", "store-b": "store-a"}


@pytest.fixture(scope="module", autouse=True)
def demo_list(settings):
    demo_prices.apply(settings.store_database_urls, LIST)
    yield
    for store in ("store-a", "store-b"):
        db_exec(settings, store, "DELETE FROM product_prices WHERE approved_by = %s", [LIST["approved_by"]])
        # TEST database only: drop the update e-mails these tests queued, so other suites' worker checks start clean.
        db_exec(settings, store, "DELETE FROM outbox WHERE kind = 'email.care_update'")


@pytest.fixture
def c(settings):
    s = dataclasses.replace(settings, store_markets={"store-a": "IN", "store-b": "IN"}, checkout_countries=("IN",),
                            shipping_config_dir=PROJECT_ROOT / "config" / "shipping")
    with make_client(s) as client:
        yield client


def agent(c, store):
    return login(c, store, AGENT[store], AGENT_PASSWORD)


def order(c, store, h, *, items=None, pay=True, deliver=True) -> dict:
    """A real order through the normal API: cart → quote → checkout → sandbox payment → staff ship → staff deliver."""
    for slug in items or SLUGS[store][:1]:
        set_stock(c.app.state.settings, store, slug, 80)
        assert c.post(f"/api/stores/{store}/cart/items", json={"slug": slug, "quantity": 1}, headers=h).status_code == 200
    q = c.post(f"/api/stores/{store}/checkout/quote", headers=h, json={"shipping_method": "standard",
               "destination": {"country": "IN", "region": "TN", "postal_code": "625521"}}).json()["cart"]
    r = c.post(f"/api/stores/{store}/checkout", headers={**h, **idem()}, json={"shipping": CUMBUM, "expected_total_cents": q["total_cents"]})
    assert r.status_code == 201, r.text
    number = r.json()["order"]["order_number"]
    if pay:
        ref = c.post(f"/api/stores/{store}/orders/{number}/payments", headers=h).json()["payment"]["reference"]
        c.post(f"/api/stores/{store}/payments/sandbox/{ref}/complete", headers=h, json={"outcome": "success"})
        assert c.post(f"/api/stores/{store}/orders/{number}/payments/verify", headers=h).json()["order"]["status"] == "processing"
    if pay and deliver:
        a = agent(c, store)
        assert c.post(f"/api/stores/{store}/staff/orders/{number}/ship", headers=a, json={
            "expected_status": "processing", "carrier": "DemoPost", "tracking_number": "TRK12345"}).status_code == 200
        assert c.post(f"/api/stores/{store}/staff/orders/{number}/deliver", headers=a, json={"expected_status": "shipped"}).status_code == 200
    detail = c.get(f"/api/stores/{store}/orders/{number}", headers=h).json()["order"]
    item_ids = [i["id"] for i in c.get(f"/api/stores/{store}/care/options?kind=complaint&order={number}", headers=h).json()["items"]]
    return {"number": number, "status": detail["status"], "items": item_ids}


def create(c, store, h, key=None, **body):
    return c.post(f"/api/stores/{store}/care/requests", headers={**h, **(idem() if key is None else {"Idempotency-Key": key})}, json=body)


# ---- complaints ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_complaint_registration_view_and_customer_visible_history(c, store):
    h, _ = new_customer(c, store)
    o = order(c, store, h)
    r = create(c, store, h, kind="complaint", category="damaged", description="The box was crushed and the item is broken.",
               order_number=o["number"], item_id=o["items"][0])
    assert r.status_code == 201, r.text
    req = r.json()["request"]
    prefix = {"store-a": "SA", "store-b": "BB"}[store]
    assert req["reference"].startswith(f"{prefix}-CMP-") and req["status"] == "open" and req["order_number"] == o["number"]
    assert req["item"]["id"] == o["items"][0] and req["can_withdraw"] and req["updates"][0]["by"] == "you"
    mine = c.get(f"/api/stores/{store}/care/requests", headers=h).json()["requests"]
    assert [x["reference"] for x in mine] == [req["reference"]]
    assert c.get(f"/api/stores/{store}/care/requests/{req['reference']}", headers=h).json()["request"]["description"].startswith("The box")
    # order-less complaint (general issue) is allowed
    assert create(c, store, h, kind="complaint", category="other", description="The website logged me out twice.").status_code == 201


@pytest.mark.parametrize("body, field", [
    ({"kind": "complaint", "category": "damaged"}, "description"),                                    # missing description
    ({"kind": "complaint", "category": "damaged", "description": "   "}, "description"),
    ({"kind": "complaint", "category": "lost_luggage", "description": "x y z"}, "category"),         # not a listed category
    ({"kind": "complaint", "category": "damaged", "description": "card 4111 1111 1111 1111 cvv 123"}, "description"),
    ({"kind": "return", "category": "damaged", "description": "broken"}, "order_number"),            # returns need an order
    ({"kind": "complaint", "category": "damaged", "description": "broken", "customer_id": 1}, "customer_id"),   # smuggled field
])
def test_complaint_missing_or_invalid_information_is_refused(c, body, field):
    h, _ = new_customer(c, "store-a")
    r = c.post("/api/stores/store-a/care/requests", headers={**h, **idem()}, json=body)
    assert r.status_code == 422, r.text
    assert field in json.dumps(r.json()["error"])
    assert c.get("/api/stores/store-a/care/requests", headers=h).json()["requests"] == []          # nothing stored


def test_duplicate_submission_same_key_returns_the_original_and_open_duplicate_is_refused(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h)
    body = {"kind": "complaint", "category": "wrong_item", "description": "I got a stove instead of a headlamp.",
            "order_number": o["number"], "item_id": o["items"][0]}
    key = "care-dup-key-0000000001"
    first = create(c, "store-a", h, key=key, **body)
    again = create(c, "store-a", h, key=key, **body)                      # double click / network retry
    assert first.status_code == 201 and again.status_code == 200 and again.json()["created"] is False
    assert again.json()["request"]["reference"] == first.json()["request"]["reference"]
    other = create(c, "store-a", h, **body)                               # a NEW submission while the first is open
    assert other.status_code == 409 and other.json()["error"]["code"] == "duplicate_request"
    assert first.json()["request"]["reference"] in json.dumps(other.json())
    assert len(c.get("/api/stores/store-a/care/requests", headers=h).json()["requests"]) == 1


def test_customers_and_stores_cannot_see_each_others_requests(c):
    h1, _ = new_customer(c, "store-a")
    h2, _ = new_customer(c, "store-a")
    ref = create(c, "store-a", h1, kind="complaint", category="other", description="Something is off.").json()["request"]["reference"]
    for path in (f"/care/requests/{ref}", ):
        assert c.get(f"/api/stores/store-a{path}", headers=h2).status_code == 404           # another customer: not found
    assert c.post(f"/api/stores/store-a/care/requests/{ref}/reply", headers=h2, json={"message": "hi"}).status_code == 404
    assert c.post(f"/api/stores/store-a/care/requests/{ref}/withdraw", headers=h2).status_code == 404
    hb, _ = new_customer(c, "store-b")
    assert c.get(f"/api/stores/store-b/care/requests/{ref}", headers=hb).status_code == 404       # other store's database
    assert c.get(f"/api/stores/store-b/care/requests/{ref}", headers=h1).status_code == 403       # store-A token at store B
    assert c.get(f"/api/stores/store-b/staff/care/{ref}", headers=agent(c, "store-b")).status_code == 404
    assert c.get(f"/api/stores/store-a/staff/care", headers=agent(c, "store-b")).status_code == 403
    assert c.get(f"/api/stores/store-a/care/requests/{ref}").status_code == 401                    # signed out
    # a customer can't use another customer's order
    o2 = order(c, "store-a", h2, deliver=False, pay=False)
    r = create(c, "store-a", h1, kind="complaint", category="other", description="x", order_number=o2["number"])
    assert r.status_code == 404


# ---- returns ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_return_eligible_order_then_staff_approve_receive_inspect_complete(c, store):
    h, _ = new_customer(c, store)
    o = order(c, store, h, items=SLUGS[store])
    opts = c.get(f"/api/stores/{store}/care/options?kind=return&order={o['number']}", headers=h).json()
    days = care_requests.return_window_days(care_requests.StoreId(store))
    assert opts["order"]["eligible"] and opts["order"]["days"] == days == {"store-a": 60, "store-b": 30}[store]
    r = create(c, store, h, kind="return", category="no_longer_needed", description="Unused, still sealed.",
               order_number=o["number"], item_id=o["items"][1])
    assert r.status_code == 201, r.text
    ref = r.json()["request"]["reference"]
    assert r.json()["request"]["status"] == "requested" and ref.split("-")[1] == "RET"
    # submitting never changes the order
    assert c.get(f"/api/stores/{store}/orders/{o['number']}", headers=h).json()["order"]["status"] == "delivered"
    a = agent(c, store)
    path = f"/api/stores/{store}/staff/care/{ref}/status"
    for frm, to in (("requested", "under_review"), ("under_review", "approved"), ("approved", "received"),
                    ("received", "inspected"), ("inspected", "completed")):
        r = c.post(path, headers=a, json={"status": to, "expected_status": frm, "message": f"Now {to}."})
        assert r.status_code == 200, r.text
    mine = c.get(f"/api/stores/{store}/care/requests/{ref}", headers=h).json()["request"]
    assert mine["status"] == "completed" and not mine["open"] and mine["resolved_at"]
    assert [u["status"] for u in mine["updates"]] == ["requested", "under_review", "approved", "received", "inspected", "completed"]
    assert c.get(f"/api/stores/{store}/orders/{o['number']}", headers=h).json()["order"]["status"] == "delivered"   # staff use order actions


def test_return_staff_rejection_needs_a_reason_the_customer_sees(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h)
    ref = create(c, "store-a", h, kind="return", category="other", description="Changed my mind.", order_number=o["number"]).json()["request"]["reference"]
    a = agent(c, "store-a")
    path = f"/api/stores/store-a/staff/care/{ref}/status"
    assert c.post(path, headers=a, json={"status": "rejected", "expected_status": "requested"}).status_code == 422   # no reason
    r = c.post(path, headers=a, json={"status": "rejected", "expected_status": "requested", "message": "Opened items can't be returned.",
                                      "note": "INTERNAL: customer opened the seal"})
    assert r.status_code == 200
    mine = c.get(f"/api/stores/store-a/care/requests/{ref}", headers=h).json()["request"]
    assert mine["status"] == "rejected" and mine["updates"][-1]["message"] == "Opened items can't be returned."
    assert "INTERNAL" not in json.dumps(mine)                                                    # internal notes never shown
    assert "INTERNAL" in json.dumps(c.get(f"/api/stores/store-a/staff/care/{ref}", headers=a).json())


@pytest.mark.parametrize("pay, deliver, reason", [(False, False, "not_delivered"), (True, False, "not_delivered")])
def test_return_ineligible_orders_are_refused_with_the_reason(c, pay, deliver, reason):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h, pay=pay, deliver=deliver)
    r = create(c, "store-a", h, kind="return", category="other", description="x", order_number=o["number"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_eligible" and reason in json.dumps(r.json())
    assert "report a problem or ask for human help" in r.json()["error"]["message"]


def test_return_window_comes_from_the_store_policy(c, settings):
    h, _ = new_customer(c, "store-b")
    o = order(c, "store-b", h)
    db_exec(settings, "store-b", "UPDATE orders SET delivered_at = now() - interval '31 days' WHERE order_number = %s", [o["number"]])
    r = create(c, "store-b", h, kind="return", category="other", description="x", order_number=o["number"])
    assert r.status_code == 409 and "30 days from delivery" in r.json()["error"]["message"]   # Bloom & Brew's own 30-day window
    db_exec(settings, "store-b", "UPDATE orders SET delivered_at = now() - interval '29 days' WHERE order_number = %s", [o["number"]])
    assert create(c, "store-b", h, kind="return", category="other", description="x", order_number=o["number"]).status_code == 201


def test_return_invalid_transitions_and_customer_cannot_change_status(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h)
    ref = create(c, "store-a", h, kind="return", category="damaged", description="Cracked lens.", order_number=o["number"]).json()["request"]["reference"]
    a = agent(c, "store-a")
    path = f"/api/stores/store-a/staff/care/{ref}/status"
    bad = c.post(path, headers=a, json={"status": "received", "expected_status": "requested"})        # can't skip approval
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "invalid_transition"
    assert c.post(path, headers=a, json={"status": "completed", "expected_status": "requested"}).status_code == 409
    stale = c.post(path, headers=a, json={"status": "under_review", "expected_status": "approved"})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_status"
    assert c.post(path, headers=h, json={"status": "approved", "expected_status": "requested"}).status_code == 403   # customer
    assert c.post(path, json={"status": "approved", "expected_status": "requested"}).status_code == 401
    assert c.get(f"/api/stores/store-a/care/requests/{ref}", headers=h).json()["request"]["status"] == "requested"


def test_customer_can_withdraw_only_before_staff_start(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h)
    ref = create(c, "store-a", h, kind="return", category="other", description="x", order_number=o["number"]).json()["request"]["reference"]
    c.post(f"/api/stores/store-a/staff/care/{ref}/status", headers=agent(c, "store-a"), json={"status": "under_review", "expected_status": "requested"})
    assert c.post(f"/api/stores/store-a/care/requests/{ref}/withdraw", headers=h).status_code == 409
    ref2 = create(c, "store-a", h, kind="complaint", category="other", description="y").json()["request"]["reference"]
    w = c.post(f"/api/stores/store-a/care/requests/{ref2}/withdraw", headers=h)
    assert w.status_code == 200 and w.json()["request"]["status"] == "withdrawn"


# ---- refunds (simulated) -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_refund_request_staff_approve_and_simulated_completion_moves_no_money(c, store, settings):
    h, _ = new_customer(c, store)
    o = order(c, store, h)
    payments_before = db_exec(settings, store, "SELECT count(*), coalesce(sum(amount_cents), 0) FROM payments")[0]
    sandbox_before = db_exec(settings, store, "SELECT count(*) FROM sandbox_payment_intents")[0][0]
    provider = c.app.state.payments
    calls = []
    for name in ("create_payment", "complete", "get_payment"):        # any provider call during the refund flow is a failure
        if hasattr(provider, name):
            orig = getattr(provider, name)
            setattr(provider, name, lambda *a, _n=name, _o=orig, **k: calls.append(_n) or _o(*a, **k))
    r = create(c, store, h, kind="refund", category="damaged", description="Arrived broken; please refund.", order_number=o["number"])
    assert r.status_code == 201, r.text
    req = r.json()["request"]
    assert req["status"] == "requested" and req["simulated"] and "no real money is transferred" in req["simulated_notice"]
    a = agent(c, store)
    path = f"/api/stores/{store}/staff/care/{req['reference']}/status"
    for frm, to in (("requested", "under_review"), ("under_review", "approved"), ("approved", "simulated_completed")):
        assert c.post(path, headers=a, json={"status": to, "expected_status": frm}).status_code == 200
    mine = c.get(f"/api/stores/{store}/care/requests/{req['reference']}", headers=h).json()["request"]
    assert mine["status"] == "simulated_completed" and "simulated" in mine["status_label"]
    assert calls == []                                                                        # no payment provider call
    assert db_exec(settings, store, "SELECT count(*), coalesce(sum(amount_cents), 0) FROM payments")[0] == payments_before
    assert db_exec(settings, store, "SELECT count(*) FROM sandbox_payment_intents")[0][0] == sandbox_before
    assert c.get(f"/api/stores/{store}/orders/{o['number']}", headers=h).json()["order"]["status"] == "delivered"
    # The care module never imports the payment providers (it only READS the payments table for eligibility).
    tree = ast.parse(inspect.getsource(care_requests))
    imported = {(n.module or "") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | \
               {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any("payment" in m for m in imported), imported
    writes = [s for s in ast.walk(tree) if isinstance(s, ast.Constant) and isinstance(s.value, str)
              and re.search(r"(INSERT INTO|UPDATE|DELETE FROM)\s+(payments|sandbox_payment_intents)", s.value)]
    assert writes == []


def test_refund_rejection_invalid_order_item_and_customer_cannot_approve(c):
    h, _ = new_customer(c, "store-b")
    unpaid = order(c, "store-b", h, pay=False, deliver=False)
    r = create(c, "store-b", h, kind="refund", category="other", description="x", order_number=unpaid["number"])
    assert r.status_code == 409 and "not_paid" in json.dumps(r.json())
    assert create(c, "store-b", h, kind="refund", category="other", description="x", order_number="BB-99999").status_code == 404
    paid = order(c, "store-b", h)
    assert create(c, "store-b", h, kind="refund", category="other", description="x", order_number=paid["number"],
                  item_id=999999).status_code == 422
    ref = create(c, "store-b", h, kind="refund", category="charged_incorrectly", description="Charged twice?",
                 order_number=paid["number"]).json()["request"]["reference"]
    path = f"/api/stores/store-b/staff/care/{ref}/status"
    assert c.post(path, headers=h, json={"status": "approved", "expected_status": "requested"}).status_code == 403
    a = agent(c, "store-b")
    assert c.post(path, headers=a, json={"status": "simulated_completed", "expected_status": "requested"}).status_code == 409
    assert c.post(path, headers=a, json={"status": "rejected", "expected_status": "requested",
                                         "message": "Only one payment was recorded."}).status_code == 200
    ha, _ = new_customer(c, "store-a")
    assert c.get(f"/api/stores/store-a/care/requests/{ref}", headers=ha).status_code == 404       # cross-store


# ---- human escalation ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_escalation_assignment_staff_response_customer_reply_and_resolution(c, store, settings):
    h, _ = new_customer(c, store)
    assert create(c, store, h, kind="escalation", description="Please call me.").status_code == 422     # missing reason
    r = create(c, store, h, kind="escalation", category="order_problem", description="I need to talk to someone about my order.")
    assert r.status_code == 201
    ref = r.json()["request"]["reference"]
    assert ref.split("-")[1] == "ESC" and r.json()["request"]["status"] == "open" and r.json()["request"]["assigned"] is False
    a = agent(c, store)
    agents = c.get(f"/api/stores/{store}/staff/care/agents", headers=a).json()["agents"]
    assert len(agents) == 1
    other_agent_id = c.get(f"/api/stores/{OTHER[store]}/staff/care/agents", headers=agent(c, OTHER[store])).json()["agents"][0]["id"]
    bad = c.post(f"/api/stores/{store}/staff/care/{ref}/assign", headers=a, json={"assignee_id": 99999})
    assert bad.status_code == 422
    s = c.post(f"/api/stores/{store}/staff/care/{ref}/assign", headers=a, json={"assignee_id": agents[0]["id"]}).json()["request"]
    assert s["status"] == "assigned" and s["assigned_to"]["id"] == agents[0]["id"]
    assert other_agent_id is not None
    c.post(f"/api/stores/{store}/staff/care/{ref}/status", headers=a, json={"status": "in_progress", "expected_status": "assigned"})
    c.post(f"/api/stores/{store}/staff/care/{ref}/notes", headers=a, json={"body": "INTERNAL: VIP customer"})
    c.post(f"/api/stores/{store}/staff/care/{ref}/messages", headers=a, json={"body": "Hello, which item is it?"})
    c.post(f"/api/stores/{store}/staff/care/{ref}/status", headers=a, json={"status": "awaiting_customer", "expected_status": "in_progress"})
    mine = c.get(f"/api/stores/{store}/care/requests/{ref}", headers=h).json()["request"]
    assert mine["status"] == "awaiting_customer" and mine["assigned"] and mine["can_reply"]
    assert any(u["message"] == "Hello, which item is it?" and u["by"] == "staff" for u in mine["updates"])
    assert "INTERNAL" not in json.dumps(mine) and agents[0]["name"] not in json.dumps(mine)        # no internal note, no staff name
    back = c.post(f"/api/stores/{store}/care/requests/{ref}/reply", headers=h, json={"message": "It's the headlamp."}).json()["request"]
    assert back["status"] == "in_progress"
    c.post(f"/api/stores/{store}/staff/care/{ref}/status", headers=a, json={"status": "resolved", "expected_status": "in_progress",
                                                                            "message": "Sorted — thanks."})
    done = c.get(f"/api/stores/{store}/care/requests/{ref}", headers=h).json()["request"]
    assert done["status"] == "resolved" and done["resolved_at"] and not done["can_reply"]
    queued = db_exec(settings, store, "SELECT count(*) FROM outbox WHERE kind = 'email.care_update' AND payload->>'reference' = %s", [ref])[0][0]
    assert queued >= 4                                                                            # customer notified of changes


def test_staff_queue_filters_search_and_unauthorized_access(c):
    h, _ = new_customer(c, "store-a")
    o = order(c, "store-a", h)
    ref = create(c, "store-a", h, kind="complaint", category="delivery", description="Late.", order_number=o["number"]).json()["request"]["reference"]
    a = agent(c, "store-a")
    by_ref = c.get(f"/api/stores/store-a/staff/care?q={ref}", headers=a).json()
    assert [x["reference"] for x in by_ref["requests"]] == [ref] and by_ref["requests"][0]["customer_name"]
    by_order = c.get(f"/api/stores/store-a/staff/care?q={o['number']}", headers=a).json()["requests"]
    assert ref in [x["reference"] for x in by_order]
    only_esc = c.get("/api/stores/store-a/staff/care?kind=escalation", headers=a).json()["requests"]
    assert all(x["kind"] == "escalation" for x in only_esc)
    assert all(x["status"] == "open" for x in c.get("/api/stores/store-a/staff/care?status=open", headers=a).json()["requests"])
    assert c.get("/api/stores/store-a/staff/care?date_from=2099-01-01", headers=a).json()["total"] == 0
    assert c.get("/api/stores/store-a/staff/care", headers=h).status_code == 403                  # customers
    assert c.get("/api/stores/store-a/staff/care").status_code == 401                             # signed out
    assert all(not x["reference"].startswith("BB-") for x in c.get("/api/stores/store-a/staff/care?limit=100", headers=a).json()["requests"])
    detail = c.get(f"/api/stores/store-a/staff/care/{ref}", headers=a).json()["request"]
    assert detail["order"]["order_number"] == o["number"] and detail["order"]["total"].startswith("₹")
    assert detail["customer"]["email"].endswith("@example.com") and detail["history"][0]["event"] == "created"

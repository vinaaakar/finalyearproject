"""Sandbox payments: provider-verified status, consistent order/payment transitions, no client trust."""

import pytest

from app.order_state import (ORDER_TRANSITIONS, PAYMENT_TRANSITIONS, InvalidTransition, can_transition,
                             transition_order)
from tests.conftest import ADDRESS_A, db_exec, idem, new_customer, set_stock

LAMP = "lumen-300-headlamp"


@pytest.fixture
def pending_order(client):
    set_stock(client.app.state.settings, "store-a", LAMP, 75)
    headers, _ = new_customer(client, "store-a")
    client.post("/api/stores/store-a/cart/items", json={"slug": LAMP, "quantity": 1}, headers=headers)
    r = client.post("/api/stores/store-a/checkout", headers={**headers, **idem()},
                    json={"shipping": ADDRESS_A, "expected_total_cents": 4595})
    assert r.status_code == 201, r.text
    return headers, r.json()["order"]["order_number"]


def start(client, headers, number):
    r = client.post(f"/api/stores/store-a/orders/{number}/payments", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["payment"]


def complete(client, headers, ref, outcome):
    return client.post(f"/api/stores/store-a/payments/sandbox/{ref}/complete", headers=headers, json={"outcome": outcome})


def verify(client, headers, number):
    return client.post(f"/api/stores/store-a/orders/{number}/payments/verify", headers=headers).json()


def test_successful_sandbox_payment_marks_order_processing(client, pending_order):
    headers, number = pending_order
    pay = start(client, headers, number)
    assert pay["sandbox"] is True and pay["status"] == "pending" and pay["amount"] == "$45.95"
    assert complete(client, headers, pay["reference"], "success").json()["sandbox"] is True
    result = verify(client, headers, number)
    assert result["payment"]["status"] == "succeeded" and result["order"]["status"] == "processing"


def test_order_not_paid_until_server_verifies(client, pending_order):
    headers, number = pending_order
    pay = start(client, headers, number)
    complete(client, headers, pay["reference"], "success")
    # The provider says "succeeded", but the order only changes when the server verifies.
    assert client.get(f"/api/stores/store-a/orders/{number}", headers=headers).json()["order"]["status"] == "pending_payment"


def test_client_claims_are_ignored(client, pending_order):
    headers, number = pending_order
    start(client, headers, number)
    # The verify endpoint takes no body; a fake "succeeded" claim is rejected outright.
    r = client.post(f"/api/stores/store-a/orders/{number}/payments/verify", headers=headers, json={"status": "succeeded"})
    assert r.json()["order"]["status"] == "pending_payment" and r.json()["payment"]["status"] == "pending"


def test_declined_payment_can_be_retried(client, pending_order):
    headers, number = pending_order
    first = start(client, headers, number)
    complete(client, headers, first["reference"], "decline")
    result = verify(client, headers, number)
    assert result["payment"]["status"] == "failed" and result["order"]["status"] == "pending_payment"
    second = start(client, headers, number)
    assert second["reference"] != first["reference"]
    complete(client, headers, second["reference"], "success")
    assert verify(client, headers, number)["order"]["status"] == "processing"


def test_start_payment_is_idempotent_while_pending(client, pending_order):
    headers, number = pending_order
    assert start(client, headers, number)["reference"] == start(client, headers, number)["reference"]


def test_sandbox_outcome_cannot_be_changed_after_completion(client, pending_order):
    headers, number = pending_order
    pay = start(client, headers, number)
    complete(client, headers, pay["reference"], "decline")
    assert complete(client, headers, pay["reference"], "success").status_code == 409


def test_amount_mismatch_is_not_accepted(client, pending_order):
    headers, number = pending_order
    pay = start(client, headers, number)
    # Simulate the provider reporting a different captured amount.
    db_exec(client.app.state.settings, "store-a", "UPDATE sandbox_payment_intents SET amount_cents = 1, status = 'succeeded' WHERE ref = %s",
            [pay["reference"]])
    result = verify(client, headers, number)
    assert result["payment"]["status"] == "failed" and result["order"]["status"] == "pending_payment"


def test_cannot_pay_paid_or_cancelled_orders(client, pending_order):
    headers, number = pending_order
    pay = start(client, headers, number)
    complete(client, headers, pay["reference"], "success")
    verify(client, headers, number)
    assert client.post(f"/api/stores/store-a/orders/{number}/payments", headers=headers).status_code == 409
    assert client.post(f"/api/stores/store-a/orders/{number}/cancel", headers=headers).status_code == 409


def test_cancelled_order_payment_cannot_be_completed(client, pending_order):
    headers, number = pending_order
    pay = start(client, headers, number)
    client.post(f"/api/stores/store-a/orders/{number}/cancel", headers=headers)
    assert complete(client, headers, pay["reference"], "success").status_code == 404


def test_other_customer_cannot_complete_or_verify(client, pending_order):
    headers, number = pending_order
    pay = start(client, headers, number)
    other, _ = new_customer(client, "store-a")
    assert complete(client, other, pay["reference"], "success").status_code == 404
    assert client.post(f"/api/stores/store-a/orders/{number}/payments/verify", headers=other).status_code == 404


def test_store_b_cannot_see_store_a_payment(client, pending_order):
    headers, number = pending_order
    pay = start(client, headers, number)
    b_headers, _ = new_customer(client, "store-b")
    r = client.post(f"/api/stores/store-b/payments/sandbox/{pay['reference']}/complete", headers=b_headers, json={"outcome": "success"})
    assert r.status_code == 404
    assert client.post(f"/api/stores/store-b/payments/sandbox/{pay['reference']}/complete", headers=headers,
                       json={"outcome": "success"}).status_code == 403


def test_health_reports_sandbox(client):
    assert client.get("/api/health").json()["payments"] == {"provider": "sandbox", "sandbox": True}


def test_live_provider_requires_authorisation(tmp_path):
    from app.config import ConfigError, load_settings
    from tests.test_platform import GOOD_ENV

    with pytest.raises(ConfigError) as exc:
        load_settings({**GOOD_ENV, "PAYMENT_PROVIDER": "stripe"}, env_file=tmp_path / "none")
    assert "PAYMENT_LIVE_AUTHORIZED" in str(exc.value)


# ---- state machine ------------------------------------------------------------------------------
def test_state_machine_rules():
    assert can_transition(ORDER_TRANSITIONS, "pending_payment", "processing")
    assert not can_transition(ORDER_TRANSITIONS, "pending_payment", "shipped")
    assert not can_transition(ORDER_TRANSITIONS, "cancelled", "processing")
    assert not can_transition(ORDER_TRANSITIONS, "delivered", "processing")
    assert all(not PAYMENT_TRANSITIONS[s] for s in ("succeeded", "failed", "cancelled"))
    with pytest.raises(InvalidTransition):
        transition_order(None, 1, "cancelled", "processing")

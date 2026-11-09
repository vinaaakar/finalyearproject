"""SANDBOX payment provider — test mode only, no real money, no card data.

It stands in for a remote provider: its state lives in `sandbox_payment_intents`, separate
from the application's `payments` table, and the application learns the outcome only by
calling `get_payment`, exactly as it would with a real provider's API.

`complete` plays the role of the provider's hosted payment page: the tester chooses
whether the simulated payment succeeds or is declined.
"""

from __future__ import annotations

import secrets
from typing import Literal

from ..db import store_connection
from ..stores import StoreId
from .base import ProviderPayment

_STATUS_MAP = {"requires_action": "pending", "succeeded": "succeeded", "declined": "failed", "cancelled": "cancelled"}


class SandboxProvider:
    name = "sandbox"
    sandbox = True

    def create_payment(self, store: StoreId, amount_cents: int, currency: str) -> ProviderPayment:
        ref = "sbx_" + secrets.token_urlsafe(18)
        with store_connection(store) as conn:
            conn.execute(
                "INSERT INTO sandbox_payment_intents (ref, amount_cents, currency, status) VALUES (%s, %s, %s, 'requires_action')",
                [ref, amount_cents, currency],
            )
        return ProviderPayment(ref, "pending", amount_cents, currency)

    def get_payment(self, store: StoreId, ref: str) -> ProviderPayment | None:
        with store_connection(store) as conn:
            row = conn.execute("SELECT ref, amount_cents, currency, status FROM sandbox_payment_intents WHERE ref = %s", [ref]).fetchone()
        if row is None:
            return None
        return ProviderPayment(row["ref"], _STATUS_MAP[row["status"]], row["amount_cents"], row["currency"])

    def complete(self, store: StoreId, ref: str, outcome: Literal["success", "decline"]) -> bool:
        """Simulated hosted-page action. Only an intent still awaiting action can be completed."""
        with store_connection(store) as conn:
            cur = conn.execute(
                "UPDATE sandbox_payment_intents SET status = %s, updated_at = now() WHERE ref = %s AND status = 'requires_action'",
                ["succeeded" if outcome == "success" else "declined", ref],
            )
            return cur.rowcount == 1

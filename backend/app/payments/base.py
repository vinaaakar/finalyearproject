"""Payment-provider interface.

The application talks to payment providers only through this interface. A provider
is the source of truth for whether money was collected: the server asks the provider
(`get_payment`) before changing any order state, and never trusts a status sent by
the browser. No raw card data ever passes through this application — a real provider
would collect it on its own hosted page or SDK.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from ..stores import StoreId

ProviderStatus = Literal["pending", "succeeded", "failed", "cancelled"]


@dataclass(frozen=True)
class ProviderPayment:
    ref: str
    status: ProviderStatus
    amount_cents: int
    currency: str


class PaymentProvider(Protocol):
    name: str
    sandbox: bool  # True = test mode, no real money can move

    def create_payment(self, store: StoreId, amount_cents: int, currency: str) -> ProviderPayment: ...

    def get_payment(self, store: StoreId, ref: str) -> ProviderPayment | None: ...


def get_provider(name: str) -> PaymentProvider:
    if name == "sandbox":
        from .sandbox import SandboxProvider

        return SandboxProvider()
    # config.load_settings already refuses anything else; this is a second guard.
    raise RuntimeError("Only the sandbox payment provider is available")

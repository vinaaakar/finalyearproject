"""Text-based phone SIMULATOR. It exercises the real call flow but places no
telephone call and is always labelled as a simulation in its responses."""

from __future__ import annotations

from typing import Any

from .base import InboundTurn, OutboundTurn, PhoneProvider

NOTICE = "SIMULATION ONLY: no real telephone call is connected."


class SimulatorProvider(PhoneProvider):
    name = "simulator"
    simulated = True

    def parse_inbound(self, payload: dict[str, Any]) -> InboundTurn:
        return InboundTurn(call_id=payload["call_id"], speech=payload.get("speech"), digits=payload.get("digits"))

    def render(self, turn: OutboundTurn) -> dict[str, Any]:
        return {
            "simulated": True,
            "notice": NOTICE,
            "call_id": turn.call_id,
            "say": turn.say,
            "expect_input": turn.expect_input,
            "hang_up": turn.hang_up,
            "transfer_to_agent": turn.transfer_to_agent,
        }

"""Provider-independent phone interface.

A telephony provider adapter (Twilio, Vonage, a SIP gateway such as Asterisk/FreeSWITCH,
...) only has to translate between its webhook format and these two dataclasses.
The call flow itself lives in `session.py` and is shared by every provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class InboundTurn:
    call_id: str
    speech: str | None = None   # transcribed caller speech
    digits: str | None = None   # DTMF keypad input


@dataclass
class OutboundTurn:
    call_id: str
    say: str
    expect_input: bool = True
    hang_up: bool = False
    transfer_to_agent: bool = False


class PhoneProvider(ABC):
    name: str
    # True only for adapters that never touch a real telephone network.
    simulated: bool

    @abstractmethod
    def parse_inbound(self, payload: dict[str, Any]) -> InboundTurn: ...

    @abstractmethod
    def render(self, turn: OutboundTurn) -> Any: ...

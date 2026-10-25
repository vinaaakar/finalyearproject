from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

EMAIL_PATTERN = r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$"


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=1, max_length=200)


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    customer: dict


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)
    channel: Literal["web_chat", "web_voice"] = "web_chat"

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str) -> str:
        v = "".join(ch for ch in v if ch.isprintable() or ch in "\n\t").strip()
        if not v:
            raise ValueError("message must not be blank")
        return v


class ChatResponse(BaseModel):
    reply: str
    intents: list[str]
    source: Literal["llm", "rules"]
    products: list[dict]
    orders: list[dict]
    requires_login: bool


class PhoneTurnRequest(BaseModel):
    # Text that a speech-to-text engine (or a tester) produced for the caller's speech, or DTMF digits.
    speech: str | None = Field(default=None, max_length=500)
    digits: str | None = Field(default=None, max_length=20, pattern=r"^[0-9*#]*$")


class PhoneCallStart(BaseModel):
    dialed_number: str | None = Field(default=None, max_length=20, pattern=r"^\+?[0-9]{5,15}$")

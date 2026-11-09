from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    # Current conversation language: used only for language-neutral messages and clarifications.
    conversation_language: Literal["ta", "en", "hi"] = "ta"
    # Receipt from /speech/transcribe for this exact text; lets the server use its own acoustic detection.
    speech_receipt: str | None = Field(default=None, max_length=600, pattern=r"^[0-9a-f]+\.[0-9a-f]{64}$")
    # Set only when the customer explicitly picked a language (e.g. after a clarification). Not detection.
    language_override: Literal["ta", "en", "hi"] | None = None

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
    cart: dict | None = None
    language: Literal["ta", "en", "hi"]
    language_status: Literal["detected", "uncertain", "neutral", "selected"]
    language_source: str
    clarification: bool = False
    # Proposed actions (links; add-to-cart and cancel buttons the customer must tap). Not yet performed.
    actions: list[dict] = []


class PhoneTurnRequest(BaseModel):
    # Text that a speech-to-text engine (or a tester) produced for the caller's speech, or DTMF digits.
    speech: str | None = Field(default=None, max_length=500)
    digits: str | None = Field(default=None, max_length=20, pattern=r"^[0-9*#]*$")


class PhoneCallStart(BaseModel):
    dialed_number: str | None = Field(default=None, max_length=20, pattern=r"^\+?[0-9]{5,15}$")


# ---- accounts ------------------------------------------------------------------------------------
COMMON_PASSWORDS = {"password123", "1234567890", "qwertyuiop", "letmein123", "password1!", "iloveyou12", "welcome123", "admin12345"}


def _clean_text(v: str) -> str:
    return " ".join("".join(ch for ch in v if ch.isprintable()).split())


def check_password_strength(password: str, email: str | None = None) -> str:
    if len(password) < 10:
        raise ValueError("password must be at least 10 characters")
    if password.lower() in COMMON_PASSWORDS or len(set(password)) < 4:
        raise ValueError("password is too easy to guess")
    if email and password.lower() == email.lower():
        raise ValueError("password must not be your email address")
    return password


class Strict(BaseModel):
    # Unknown fields are rejected, so clients cannot smuggle in e.g. "role" or card numbers.
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(Strict):
    email: str = Field(min_length=3, max_length=254, pattern=EMAIL_PATTERN)
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        v = _clean_text(v)
        if not v:
            raise ValueError("name must not be blank")
        return v

    @model_validator(mode="after")
    def strong_password(self):
        check_password_strength(self.password, self.email)
        return self


class PasswordResetRequest(Strict):
    email: str = Field(min_length=3, max_length=254, pattern=EMAIL_PATTERN)


class PasswordResetConfirm(Strict):
    token: str = Field(min_length=20, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    new_password: str = Field(min_length=1, max_length=200)

    @field_validator("new_password")
    @classmethod
    def strong(cls, v: str) -> str:
        return check_password_strength(v)


# ---- cart & checkout -------------------------------------------------------------------------------
Slug = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9-]+$")


class CartItemAdd(Strict):
    slug: str = Slug
    quantity: int = Field(default=1, ge=1, le=10)


class CartItemUpdate(Strict):
    quantity: int = Field(ge=0, le=10)


class ShippingAddress(Strict):
    full_name: str = Field(min_length=1, max_length=100)
    line1: str = Field(min_length=1, max_length=120)
    line2: str | None = Field(default=None, max_length=120)
    city: str = Field(min_length=1, max_length=80)
    region: str = Field(pattern=r"^[A-Za-z]{2}$", description="US state code")
    postal_code: str = Field(pattern=r"^\d{5}(-\d{4})?$")
    country: Literal["US"] = "US"

    @field_validator("full_name", "line1", "line2", "city")
    @classmethod
    def clean(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = _clean_text(v)
        return v

    @field_validator("full_name", "line1", "city")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("region")
    @classmethod
    def us_state(cls, v: str) -> str:
        from .stores import US_REGIONS

        v = v.upper()
        if v not in US_REGIONS:
            raise ValueError("must be a US state code")
        return v


ShippingMethod = Literal["standard", "expedited"]


class QuoteRequest(Strict):
    shipping_method: ShippingMethod = "standard"


class CheckoutRequest(Strict):
    shipping: ShippingAddress
    shipping_method: ShippingMethod = "standard"
    # The total the customer reviewed. If the server's total differs, checkout stops and asks for a new review.
    expected_total_cents: int = Field(ge=0, le=10_000_000)


class SandboxCompleteRequest(Strict):
    outcome: Literal["success", "decline"]


class SynthesizeRequest(Strict):
    text: str = Field(min_length=1, max_length=1000)
    language: Literal["ta", "en", "hi"] | None = None

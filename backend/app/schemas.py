from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EMAIL_PATTERN = r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$"


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=1, max_length=200)


class LoginResponse(BaseModel):
    # Cookie mode (AUTH_COOKIES=true): the token is ONLY in an HttpOnly cookie, never given to page scripts.
    access_token: str | None
    token_type: Literal["bearer", "cookie"] = "bearer"
    expires_in: int
    customer: dict
    csrf_token: str | None = None


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
    # A customer-care request being put together in this conversation (returned by the server in the previous reply).
    # Only a convenience: every field is re-validated, and the request is created only after an explicit "yes".
    care_draft: dict | None = None

    @field_validator("care_draft")
    @classmethod
    def small_draft(cls, v):
        return None if v is not None and len(str(v)) > 3000 else v     # oversized: ignored (the flow starts over)

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
    # Customer-care request in progress (send it back with the next message), and the reference of a request the
    # server has just created (only ever set from the database's own record).
    care_draft: dict | None = None
    care_reference: str | None = None
    # Server-side latency in milliseconds ("total", and "llm" when the local model was called) — for measuring, not display.
    timing: dict[str, int] = {}


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
    # Country-specific rules (states / union territories, ZIP vs PIN, phone) are applied by commerce.validate_address
    # from app/markets.py; the schema only bounds the shape.
    region: str = Field(pattern=r"^[A-Za-z]{2}$", description="state / union territory code of `country`")
    postal_code: str = Field(pattern=r"^\d{5}(-\d{4})?$|^\d{6}$", description="US ZIP / ZIP+4 or Indian PIN")
    country: Literal["US", "IN"] = "US"
    phone: str | None = Field(default=None, max_length=20, pattern=r"^[+0-9 ().\-]{7,20}$")
    label: str | None = Field(default=None, max_length=50)

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
    def upper_region(cls, v: str) -> str:
        # Which codes are valid depends on `country` (US states, Indian states / union territories): checked by
        # commerce.validate_address with app/markets.py. (A US-only check here once refused every Indian state whose
        # code isn't also a US one — e.g. Karnataka "KA" — while Tamil Nadu "TN" passed only as Tennessee.)
        return v.upper()


class AddressCreate(Strict):
    label: str = Field(default="Home", min_length=1, max_length=50)
    full_name: str = Field(min_length=1, max_length=100)
    line1: str = Field(min_length=1, max_length=120)
    line2: str | None = Field(default=None, max_length=120)
    city: str = Field(min_length=1, max_length=80)
    region: str = Field(pattern=r"^[A-Za-z]{2}$")
    postal_code: str = Field(pattern=r"^\d{5}(-\d{4})?$|^\d{6}$")
    country: Literal["US", "IN"] = "IN"
    phone: str | None = Field(default=None, max_length=20, pattern=r"^[+0-9 ().\-]{7,20}$")
    is_default: bool = False

    @field_validator("label", "full_name", "line1", "line2", "city")
    @classmethod
    def clean(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _clean_text(v)

    @field_validator("label", "full_name", "line1", "city")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("region")
    @classmethod
    def upper_region(cls, v: str) -> str:
        return v.upper()


class AddressUpdate(Strict):
    label: str | None = Field(default=None, min_length=1, max_length=50)
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    line1: str | None = Field(default=None, min_length=1, max_length=120)
    line2: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, min_length=1, max_length=80)
    region: str | None = Field(default=None, pattern=r"^[A-Za-z]{2}$")
    postal_code: str | None = Field(default=None, pattern=r"^\d{5}(-\d{4})?$|^\d{6}$")
    country: Literal["US", "IN"] | None = None
    phone: str | None = Field(default=None, max_length=20, pattern=r"^[+0-9 ().\-]{7,20}$")
    is_default: bool | None = None

    @field_validator("label", "full_name", "line1", "line2", "city")
    @classmethod
    def clean(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _clean_text(v)

    @field_validator("region")
    @classmethod
    def upper_region(cls, v: str | None) -> str | None:
        return v.upper() if v else None


ShippingMethod = Literal["standard", "expedited"]


class Destination(Strict):
    country: Literal["US", "IN"] = "US"
    region: str | None = Field(default=None, pattern=r"^[A-Za-z]{2}$")
    postal_code: str | None = Field(default=None, max_length=10)


class QuoteRequest(Strict):
    shipping_method: ShippingMethod = "standard"
    destination: Destination | None = None      # omitted = the store's US rates, exactly as before


class CheckoutRequest(Strict):
    shipping: ShippingAddress
    shipping_method: ShippingMethod = "standard"
    # The total the customer reviewed. If the server's total differs, checkout stops and asks for a new review.
    expected_total_cents: int = Field(ge=0, le=10_000_000)
    # Opt-in: the address is copied to the customer's address book only when the customer asks for it.
    save_address: bool = False
    make_default: bool = False
    address_label: str = Field(default="Home", min_length=1, max_length=50)



class SandboxCompleteRequest(Strict):
    outcome: Literal["success", "decline"]


class SynthesizeRequest(Strict):
    text: str = Field(min_length=1, max_length=1000)
    language: Literal["ta", "en", "hi"] | None = None

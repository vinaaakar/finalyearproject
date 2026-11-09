"""Password hashing (scrypt) and compact HMAC-signed access tokens.

Tokens carry the store id they were issued for; a token from one store is
rejected by every endpoint of the other store.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from .stores import StoreId

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    return hmac.compare_digest(digest.hex(), digest_hex)


def new_opaque_token() -> str:
    """Random bearer value for sessions, guest carts and password resets."""
    return secrets.token_urlsafe(32)


def hash_opaque_token(token: str) -> str:
    """Opaque tokens are stored only as SHA-256 hashes, so a database leak does not reveal usable tokens."""
    return hashlib.sha256(token.encode()).hexdigest()


# Used to equalise timing when the email does not exist.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))


@dataclass(frozen=True)
class Principal:
    customer_id: int
    store: StoreId
    role: str  # "customer" | "agent"
    name: str
    # Random id of the server-side session row this token belongs to (see repositories.create_session).
    session_id: str = ""


class TokenError(Exception):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def issue_token(principal: Principal, secret: str, ttl_minutes: int) -> str:
    now = int(time.time())
    payload = {
        "sub": principal.customer_id,
        "store": principal.store.value,
        "role": principal.role,
        "name": principal.name,
        "sid": principal.session_id,
        "iat": now,
        "exp": now + ttl_minutes * 60,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def decode_token(token: str, secret: str) -> Principal:
    try:
        body, sig = token.split(".")
    except ValueError as exc:
        raise TokenError("malformed") from exc
    expected = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise TokenError("bad signature")
    try:
        payload = json.loads(_unb64(body))
        if payload["exp"] < time.time():
            raise TokenError("expired")
        return Principal(
            customer_id=int(payload["sub"]),
            store=StoreId(payload["store"]),
            role=payload["role"],
            name=str(payload.get("name", "")),
            session_id=str(payload.get("sid", "")),
        )
    except TokenError:
        raise
    except Exception as exc:
        raise TokenError("invalid payload") from exc

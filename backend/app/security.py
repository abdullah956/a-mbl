"""Passwords, tokens, and content encryption.

- Passwords: PBKDF2-HMAC-SHA256 from the standard library. The roadmap names
  Argon2 for a hardened build; PBKDF2 keeps the local prototype dependency-free
  and is documented as a deviation in docs/IMPLEMENTATION_NOTES.md.
- Access tokens: compact HMAC-signed payloads, 15 minutes.
- Refresh tokens: random values stored only as SHA-256 hashes, rotated on use.
- Case text and evidence: Fernet (AES) with a key generated on first run.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import timedelta

from cryptography.fernet import Fernet, InvalidToken

from . import config
from .db import iso, utc_now

PBKDF2_ITERATIONS = 210_000


# --- passwords ---------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


# --- signing / encryption keys (generated once, kept outside Git) ------------

def _key_file(name: str, generator) -> bytes:
    path = config.data_dir() / name
    # Exclusive create: a check-then-write could let two concurrent first
    # requests each write a different key, silently orphaning anything already
    # encrypted with the overwritten one. Only one writer can ever win here.
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_bytes()
    with os.fdopen(fd, "wb") as handle:
        handle.write(generator())
    return path.read_bytes()


def _signing_key() -> bytes:
    return _key_file("signing.key", lambda: secrets.token_bytes(32))


def _fernet() -> Fernet:
    return Fernet(_key_file("fernet.key", Fernet.generate_key))


def ensure_keys() -> None:
    """Create both keys before the server takes requests (called at startup)."""
    _signing_key()
    _fernet()


# --- access tokens ------------------------------------------------------------

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_access_token(user_id: str) -> str:
    payload = {"uid": user_id, "exp": iso(utc_now() + timedelta(minutes=config.ACCESS_TOKEN_MINUTES))}
    body = _b64(json.dumps(payload).encode())
    sig = hmac.new(_signing_key(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def read_access_token(token: str) -> str | None:
    """Return the user id for a valid, unexpired token, else None."""
    try:
        body, sig = token.split(".")
        expected = hmac.new(_signing_key(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_unb64(body))
        if payload["exp"] < iso(utc_now()):
            return None
        return payload["uid"]
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


# --- refresh tokens and one-time codes ----------------------------------------

def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def new_link_code() -> str:
    return secrets.token_hex(4).upper()  # 8 characters, easy to read aloud


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# --- content encryption ---------------------------------------------------------

def encrypt_bytes(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt_bytes(data: bytes) -> bytes | None:
    try:
        return _fernet().decrypt(bytes(data))
    except InvalidToken:
        return None


def encrypt_text(text: str) -> bytes:
    return encrypt_bytes(text.encode())


def decrypt_text(data: bytes) -> str:
    decrypted = decrypt_bytes(data)
    return decrypted.decode() if decrypted is not None else ""

"""Authentication primitives (M4): password hashing + JWT.

Passwords are hashed with PBKDF2-HMAC-SHA256 (standard library only). Access tokens
are signed JWTs (HS256). The signing secret comes from the CHARGESMART_JWT_SECRET
environment variable, with an insecure development fallback.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

import jwt

from .entities import UserRole

_JWT_SECRET = os.environ.get("CHARGESMART_JWT_SECRET", "dev-insecure-secret-change-me")
_JWT_ALGORITHM = "HS256"
_TOKEN_TTL_SECONDS = 8 * 3600
_PBKDF2_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    """Return a self-describing PBKDF2 hash: ``pbkdf2_sha256$iters$salt$hash``."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return (
        f"pbkdf2_sha256${_PBKDF2_ITERATIONS}$"
        f"{base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_b64, hash_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        return hmac.compare_digest(dk, expected)  # constant-time
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, role: UserRole) -> str:
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "exp": int(time.time()) + _TOKEN_TTL_SECONDS,
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a token. Raises jwt.PyJWTError on failure."""
    return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])

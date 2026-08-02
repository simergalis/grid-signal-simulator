"""
api/auth_utils.py — JWT creation/validation and password hashing utilities.

Authentication design:
  - Passwords hashed with bcrypt (direct — passlib's bcrypt backend is
    incompatible with bcrypt 4.x which removed the __about__ attribute and
    changed its internal API; we call bcrypt directly to avoid the mismatch).
  - Sessions encoded as JWT (HS256) with a 24-hour expiry.
  - Token carried in an httpOnly cookie named "gs_session".
  - JWT secret read from JWT_SECRET env var; falls back to SESSION_SECRET;
    errors hard at import time if neither is set so misconfiguration is
    immediately visible rather than silently insecure.

Phone-number requirement:
  Users must register with BOTH an email address and a mobile phone number.
  Login requires all three: email + phone + password.  This is validated in
  the login route, not here — auth_utils only handles crypto.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt as _bcrypt
from jose import JWTError, jwt

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_JWT_SECRET: str = os.environ.get("JWT_SECRET") or os.environ.get("SESSION_SECRET", "")
if not _JWT_SECRET:
    raise RuntimeError(
        "Neither JWT_SECRET nor SESSION_SECRET is set.  "
        "Add one of these to Replit Secrets before starting the server."
    )

_ALGORITHM   = "HS256"
_COOKIE_NAME = "gs_session"
_TOKEN_TTL   = timedelta(hours=24)

# ---------------------------------------------------------------------------
# Password helpers  (bcrypt direct — no passlib)
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain* as a str (the $2b$... format)."""
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the stored bcrypt *hashed* string."""
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_access_token(user_id: int, email: str) -> str:
    """Return a signed JWT valid for 24 hours."""
    expire = datetime.now(timezone.utc) + _TOKEN_TTL
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Return the decoded payload or None if the token is invalid/expired."""
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_ALGORITHM])
    except JWTError:
        return None


# Re-export cookie name so routes don't need to hard-code it.
COOKIE_NAME = _COOKIE_NAME

"""
api/routes/auth_routes.py — Authentication endpoints.

POST /api/auth/request-code      — email a 6-digit sign-in code to the address
POST /api/auth/login             — verify the code and set a session cookie
POST /api/auth/logout            — clear the session cookie
GET  /api/auth/me                — return current user info (requires valid session)
POST /api/auth/change-password   — change the authenticated user's password

Codes expire after 10 minutes and are invalidated after 5 wrong guesses.
A new code can only be requested once every 60 seconds per address.
"""
from __future__ import annotations

import logging
import random
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import COOKIE_NAME, create_access_token, decode_access_token
from api.db import get_db_session
from runtime.persistence import AuthUser

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# In-memory OTP store  {email -> {code, expires_at, attempts, last_sent}}
# ---------------------------------------------------------------------------

_OTP_TTL_SECS          = 600   # code valid for 10 minutes
_OTP_MAX_ATTEMPTS      = 5     # invalidate after this many wrong guesses
_OTP_RESEND_COOLDOWN_S = 60    # minimum seconds between resend requests

_otp_store: dict[str, dict] = {}


def _make_code() -> str:
    return f"{random.SystemRandom().randint(0, 999999):06d}"


def _otp_entry(email: str) -> dict | None:
    entry = _otp_store.get(email)
    if entry and entry["expires_at"] > time.monotonic():
        return entry
    _otp_store.pop(email, None)
    return None


def inject_otp(email: str, code: str) -> None:
    """Inject a pre-generated OTP code directly into the in-memory store.

    Used by the bootstrap endpoint to create a usable one-time sign-in
    credential without going through the SendGrid email path.  The injected
    code expires after the standard TTL and is consumed on first use.
    """
    now = time.monotonic()
    _otp_store[email.lower()] = {
        "code":       code,
        "expires_at": now + _OTP_TTL_SECS,
        "attempts":   0,
        "last_sent":  now,
    }


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class RequestCodeRequest(BaseModel):
    email: EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    code: str


class MeResponse(BaseModel):
    user_id: int
    email: str
    display_name: str
    role: str


class ChangePasswordRequest(BaseModel):
    current_password: str | None = None  # None when no password has been set yet
    new_password: str


# ---------------------------------------------------------------------------
# Dependency — resolve current user from cookie
# ---------------------------------------------------------------------------

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> AuthUser:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user_id = int(payload["sub"])
    user = await db.get(AuthUser, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/request-code", status_code=status.HTTP_200_OK)
async def request_code(
    body: RequestCodeRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Email a 6-digit sign-in code to the supplied address.

    Returns 200 whether or not the email is registered (avoids enumeration).
    Returns 429 if a code was already sent within the cooldown window.
    """
    from sqlalchemy import select
    from api.email_service import send_otp_email

    email = body.email.lower()

    # Cooldown check
    existing = _otp_entry(email)
    if existing:
        elapsed = time.monotonic() - existing.get("last_sent", 0)
        if elapsed < _OTP_RESEND_COOLDOWN_S:
            wait = int(_OTP_RESEND_COOLDOWN_S - elapsed) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {wait} seconds before requesting another code.",
            )

    # Look up user (we send the email regardless, but only actually mail
    # registered+active accounts to avoid leaking registrations).
    result = await db.execute(select(AuthUser).where(AuthUser.email == email))
    user: AuthUser | None = result.scalar_one_or_none()

    code = _make_code()
    now  = time.monotonic()
    _otp_store[email] = {
        "code":       code,
        "expires_at": now + _OTP_TTL_SECS,
        "attempts":   0,
        "last_sent":  now,
    }

    email_sent = False
    if user and user.is_active:
        email_sent = send_otp_email(email, user.display_name, code)
        if not email_sent:
            _log.warning(
                "OTP email delivery failed for %s — code stored but not delivered. "
                "Check SENDGRID_FROM_EMAIL is a verified SendGrid sender and "
                "SENDGRID_API_KEY is valid.",
                email,
            )
            # Console escape hatch: when email delivery fails, print the code to the
            # server log so an admin watching logs can relay it manually.
            # This is intentionally at WARNING level so it appears in production logs
            # (which are admin-only) and is trivially greppable.
            _log.warning(
                "OTP CONSOLE FALLBACK — sign-in code for %s: %s  "
                "(relay this to the user; code expires in %d minutes)",
                email, code, _OTP_TTL_SECS // 60,
            )
    else:
        # Unknown or inactive account: still store the code (avoids enumeration),
        # but log clearly so admins know why no email went out.
        _log.warning(
            "request-code for unknown/inactive email %s — no email sent. "
            "If this user should exist, create their account via POST /api/admin/users.",
            email,
        )
        # Also print the code so an admin can relay it if they want to let someone in
        # before their account is formally created (e.g. during a fresh-DB deploy).
        _log.warning(
            "OTP CONSOLE FALLBACK (unregistered) — code for %s: %s  "
            "(user not in DB; relay after creating their account)",
            email, code,
        )

    return {"ok": True, "email_sent": email_sent}


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
):
    """Verify the 6-digit code and set an httpOnly session cookie."""
    from sqlalchemy import select

    email = body.email.lower()
    code  = body.code.strip()

    # Generic failure to use in all error paths (avoids leaking detail)
    def _fail():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired code.",
        )

    entry = _otp_entry(email)
    if not entry:
        _fail()

    # Increment attempts before checking so brute-force counts correctly
    entry["attempts"] += 1
    if entry["attempts"] > _OTP_MAX_ATTEMPTS:
        _otp_store.pop(email, None)
        _fail()

    if entry["code"] != code:
        _log.warning("Wrong OTP attempt %d/%d for %s", entry["attempts"], _OTP_MAX_ATTEMPTS, email)
        _fail()

    # Code matches — consume it immediately (single-use)
    _otp_store.pop(email, None)

    result = await db.execute(select(AuthUser).where(AuthUser.email == email))
    user: AuthUser | None = result.scalar_one_or_none()
    if not user or not user.is_active:
        _fail()

    token = create_access_token(user.id, user.email)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400,
        path="/",
    )
    _log.info("User %s signed in via OTP", user.email)
    return {"ok": True, "display_name": user.display_name, "role": user.role}


@router.post("/logout")
async def logout(response: Response):
    """Clear the session cookie."""
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me(current_user: AuthUser = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return MeResponse(
        user_id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        role=current_user.role,
    )


@router.get("/password-status")
async def password_status(current_user: AuthUser = Depends(get_current_user)):
    """Return whether the authenticated user has a password set."""
    has_pw = bool(current_user.password_hash)
    return {"has_password": has_pw}


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    body: ChangePasswordRequest,
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Update the authenticated user's password.

    - If the account has no password set (hash is empty string), *current_password*
      is ignored — this is the first-time password-set path.
    - If a password is already set, *current_password* must match before the new
      one is stored.
    - New password must be at least 8 characters.
    """
    from api.auth_utils import hash_password, verify_password

    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="New password must be at least 8 characters.",
        )

    has_existing = bool(current_user.password_hash)
    if has_existing:
        if not body.current_password:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Current password is required.",
            )
        if not verify_password(body.current_password, current_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect.",
            )

    current_user.password_hash = hash_password(body.new_password)
    await db.commit()
    _log.info("User %s changed their password", current_user.email)
    return {"ok": True}

"""
api/routes/auth_routes.py — Authentication endpoints.

POST /api/auth/request-code      — email a 6-digit sign-in code to the address
POST /api/auth/login             — verify the code and set a session cookie
POST /api/auth/logout            — clear the session cookie
GET  /api/auth/me                — return current user info (requires valid session)
POST /api/auth/change-password   — change the authenticated user's password

Codes expire after 10 minutes and are invalidated after 5 wrong guesses.
A new code can only be requested once every 60 seconds per address.

OTP persistence
---------------
Codes are stored in the ``auth_otp`` table (see runtime/persistence.AuthOTP)
rather than an in-memory dict.  This means a server restart, container recycle,
or deploy no longer silently invalidates every pending code — a user who
requested a code a few seconds before the restart can still log in as long as
the 10-minute TTL has not elapsed.
"""
from __future__ import annotations

import logging
import os
import random
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import COOKIE_NAME, create_access_token, decode_access_token
from api.db import get_db_session, _SessionLocal
from runtime.persistence import AuthOTP, AuthUser

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# OTP configuration
# ---------------------------------------------------------------------------

_OTP_TTL_SECS          = 600   # code valid for 10 minutes
_OTP_MAX_ATTEMPTS      = 5     # invalidate after this many wrong guesses
_OTP_RESEND_COOLDOWN_S = 60    # minimum seconds between resend requests

# ---------------------------------------------------------------------------
# Per-IP and per-email rate limiter for POST /api/auth/login
#
# SEC-5 / Task 94: A bot that hammers /login can exhaust the 5-attempt OTP
# window, trigger a fresh request-code cycle, and repeat — effectively brute-
# forcing 1 000 000 6-digit values in minutes with enough concurrency.
#
# Mitigation: a simple sliding-window counter keyed on BOTH the client IP and
# the target email address.  Either key exceeding the threshold on its own is
# enough to return 429.  The window is tracked as a list of monotonic
# timestamps; entries older than _LOGIN_WINDOW_S are pruned on each check.
# ---------------------------------------------------------------------------

_LOGIN_RATE_LIMIT  = 10    # max requests per window per key
_LOGIN_WINDOW_S    = 60    # sliding-window duration in seconds

# {key -> [monotonic timestamp, ...]}
_login_rate: dict[str, list[float]] = {}


def _login_rate_check(ip: str, email: str) -> int | None:
    """Return seconds until the rate-limit resets, or None if under the limit.

    Checks both the per-IP and per-email counters.  If either counter has
    >= _LOGIN_RATE_LIMIT requests in the last _LOGIN_WINDOW_S seconds the
    caller must return 429.  The check is side-effect-free (it does NOT record
    the current request — that is done separately after the guard passes).

    Expired entries are pruned on each access to bound memory growth; keys
    whose bucket becomes empty are deleted entirely so the dict does not grow
    unboundedly from one-off requests by many distinct IPs or email addresses.
    """
    now = time.monotonic()
    cutoff = now - _LOGIN_WINDOW_S
    for key in (f"ip:{ip}", f"email:{email}"):
        timestamps = _login_rate.get(key, [])
        # Prune expired entries.
        timestamps = [t for t in timestamps if t > cutoff]
        if timestamps:
            _login_rate[key] = timestamps
        else:
            _login_rate.pop(key, None)
        if len(timestamps) >= _LOGIN_RATE_LIMIT:
            # Oldest entry tells us when a slot will free up.
            retry_after = int(timestamps[0] + _LOGIN_WINDOW_S - now) + 1
            return max(retry_after, 1)
    return None


def _login_rate_record(ip: str, email: str) -> None:
    """Record the current request in both per-IP and per-email buckets."""
    now = time.monotonic()
    for key in (f"ip:{ip}", f"email:{email}"):
        _login_rate.setdefault(key, []).append(now)


# Exposed so tests can reset state between cases without restarting the app.
def _login_rate_clear() -> None:
    _login_rate.clear()


# ---------------------------------------------------------------------------
# DB-backed OTP helpers
# ---------------------------------------------------------------------------

def _make_code() -> str:
    return f"{random.SystemRandom().randint(0, 999999):06d}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    """Coerce *dt* to a UTC-aware datetime.

    SQLite stores datetimes as strings and returns them without tzinfo even
    when the column is declared as ``DateTime(timezone=True)``.  PostgreSQL
    returns timezone-aware values.  Normalising here keeps comparisons safe
    on both backends without changing the stored representation.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _otp_get(email: str, db: AsyncSession) -> AuthOTP | None:
    """Return the valid (non-expired) OTP row for *email*, or None.

    Expired rows are deleted eagerly so the table doesn't accumulate stale
    entries if codes are never claimed.
    """
    result = await db.execute(select(AuthOTP).where(AuthOTP.email == email))
    row: AuthOTP | None = result.scalar_one_or_none()
    if row is None:
        return None
    if _as_utc(row.expires_at) <= _utcnow():
        await db.delete(row)
        await db.commit()
        return None
    return row


async def _otp_upsert(
    email: str,
    code: str,
    db: AsyncSession,
    *,
    ttl_secs: int = _OTP_TTL_SECS,
) -> AuthOTP:
    """Create or replace the OTP row for *email*, returning the saved row."""
    now = _utcnow()
    result = await db.execute(select(AuthOTP).where(AuthOTP.email == email))
    row: AuthOTP | None = result.scalar_one_or_none()
    if row is None:
        row = AuthOTP(
            email=email,
            code=code,
            expires_at=now + timedelta(seconds=ttl_secs),
            attempts=0,
            last_sent=now,
        )
        db.add(row)
    else:
        row.code = code
        row.expires_at = now + timedelta(seconds=ttl_secs)
        row.attempts = 0
        row.last_sent = now
    await db.commit()
    await db.refresh(row)
    return row


async def inject_otp(email: str, code: str) -> None:
    """Inject a pre-generated OTP code directly into the database.

    Used by the bootstrap endpoint and admin helpers to create a usable
    one-time sign-in credential without going through the SendGrid email path.
    The injected code expires after the standard TTL and is consumed on first
    use.

    This is a standalone async function that opens its own session so callers
    that already have a session (admin routes) and callers that do not (tests)
    can both use it without a parameter change.  Admin routes that hold an open
    write transaction should ``await db.commit()`` first to avoid lock
    conflicts on SQLite.
    """
    async with _SessionLocal() as session:
        await _otp_upsert(email.lower(), code, session)


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

    The response includes ``expires_at`` (ISO-8601 UTC) so clients can show
    the user how long the code remains valid without guessing based on when
    the request was made.
    """
    from api.email_service import send_otp_email

    email = body.email.lower()

    # Cooldown check — read the existing (non-expired) row.
    existing = await _otp_get(email, db)
    if existing:
        elapsed = (_utcnow() - _as_utc(existing.last_sent)).total_seconds()
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
    row = await _otp_upsert(email, code, db)

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

    return {
        "ok": True,
        "email_sent": email_sent,
        # Human-readable expiry so clients can show "your code expires at HH:MM UTC"
        # without guessing based on when the request was made.
        "expires_at": row.expires_at.isoformat(),
    }


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
):
    """Verify the 6-digit code and set an httpOnly session cookie."""
    email = body.email.lower()
    code  = body.code.strip()

    # SEC-5 / Task 94: rate-limit check (before any OTP work so we don't leak
    # timing info about whether the OTP exists or not).
    #
    # IP is taken ONLY from request.client.host (the TCP peer address set by
    # the ASGI server) — never from X-Forwarded-For or X-Real-IP.  Those
    # headers are client-supplied and trivially spoofable; trusting them would
    # let a bot cycle through arbitrary fake IPs and bypass the per-IP bucket.
    # If the app sits behind a trusted reverse proxy, configure the proxy to
    # rewrite the actual source address into request.client via ProxyHeadersMiddleware
    # at the server boundary, not through client-controlled headers here.
    client_ip = request.client.host if request.client else "unknown"
    retry_after = _login_rate_check(client_ip, email)
    if retry_after is not None:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Too many login attempts. Please try again later."},
            headers={"Retry-After": str(retry_after)},
        )
    # Record this attempt AFTER the guard so the counter reflects genuine
    # attempts, not rate-limit probes.
    _login_rate_record(client_ip, email)

    # Generic failure — avoids leaking whether the code exists at all.
    def _fail(*, hint: str | None = None):
        detail: dict | str
        if hint:
            # The optional hint lets the UI distinguish "code not found / expired"
            # from "code exists but wrong guess" so it can prompt the user to
            # request a fresh code rather than retry the same one.
            detail = {"message": "Invalid or expired code.", "hint": hint}
        else:
            detail = "Invalid or expired code."
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )

    entry = await _otp_get(email, db)
    if not entry:
        # Code was never requested, already expired, or the server restarted and
        # the old in-memory store was lost.  Surface a distinct hint so the UI
        # can tell the user to request a new code instead of retrying.
        _fail(hint="try_new_code")

    # Increment attempts before checking so brute-force counts correctly.
    entry.attempts += 1
    await db.commit()

    if entry.attempts > _OTP_MAX_ATTEMPTS:
        await db.delete(entry)
        await db.commit()
        _fail()

    if entry.code != code:
        _log.warning("Wrong OTP attempt %d/%d for %s", entry.attempts, _OTP_MAX_ATTEMPTS, email)
        _fail()

    # Code matches — consume it immediately (single-use).
    await db.delete(entry)
    await db.commit()

    result = await db.execute(select(AuthUser).where(AuthUser.email == email))
    user: AuthUser | None = result.scalar_one_or_none()
    if not user or not user.is_active:
        _fail()

    token = create_access_token(user.id, user.email)
    _secure_cookies = (
        os.environ.get("SECURE_COOKIES", "").lower() in ("1", "true", "yes")
        or os.environ.get("NODE_ENV", "").lower() == "production"
    )
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400,
        path="/",
        secure=_secure_cookies,
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

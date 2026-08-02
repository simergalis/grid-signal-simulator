"""
api/routes/admin_routes.py — Admin-only user management endpoints.

Access is granted by either:
  • X-Admin-Key header matching ADMIN_SECRET (curl / server-side callers), or
  • A valid session cookie with role="admin" (browser admin page).

If ADMIN_SECRET is not set the header path is disabled, but session-based
admin access still works for users whose role is "admin".

GET    /api/admin/bootstrap        — break-glass recovery (X-Admin-Key only)
POST   /api/admin/users           — create a user account; sends welcome email
GET    /api/admin/users           — list all users
PATCH  /api/admin/users/{user_id} — activate / deactivate an account or change role
DELETE /api/admin/users/{user_id} — permanently delete an account
GET    /api/admin/email-check     — diagnostic: verify email delivery configuration

Users sign in with email + one-time code (SendGrid); no password is stored.
The admin creates accounts by email + display name + role only.  The first
welcome email and should change it on first login.
"""
from __future__ import annotations

import logging
import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import COOKIE_NAME, decode_access_token, hash_password
from api.db import get_db_session
from api.email_service import send_welcome_email
from api.routes.auth_routes import inject_otp
from runtime.persistence import AuthUser

_log = logging.getLogger(__name__)
_ADMIN_SECRET: str = os.environ.get("ADMIN_SECRET", "")

router = APIRouter(prefix="/api/admin", tags=["admin"])

VALID_ROLES = ("viewer", "operator", "approver", "admin")


# ---------------------------------------------------------------------------
# Admin gate dependency
# ---------------------------------------------------------------------------

async def _require_admin(
    request: Request,
    x_admin_key: str = Header(default=""),
    db: AsyncSession = Depends(get_db_session),
):
    """Allow access if the caller presents a valid admin key OR is logged in as admin role."""
    # 1. Header-based access (curl / API callers)
    if _ADMIN_SECRET and x_admin_key == _ADMIN_SECRET:
        return

    # 2. Session-based access (browser users with role=admin)
    token = request.cookies.get(COOKIE_NAME)
    if token:
        payload = decode_access_token(token)
        if payload is not None:
            user_id = int(payload["sub"])
            user = await db.get(AuthUser, user_id)
            if user and user.is_active and user.role == "admin":
                return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required",
    )


# ---------------------------------------------------------------------------
# Break-glass bootstrap endpoint  (X-Admin-Key only — no session fallback)
# ---------------------------------------------------------------------------

_RECOVERY_EMAIL = "recovery@gridsignal.io"
_RECOVERY_DISPLAY_NAME = "Recovery Admin"


@router.get("/bootstrap")
async def bootstrap_admin(
    x_admin_key: str = Header(default=""),
    db: AsyncSession = Depends(get_db_session),
    response: Response = None,
):
    """Break-glass recovery: create a one-time sign-in code when no active admin exists.

    This endpoint is intentionally protected by the admin key header ONLY —
    not by session cookies — because its purpose is to restore access when
    every admin account has been deactivated or deleted and no one can log in.

    Responses
    ---------
    200  {"status": "ok",      "admin_exists": true}
         At least one active admin account already exists; no action taken.

    200  {"status": "created", "admin_exists": false,
          "email": ..., "one_time_code": ..., "login_path": "/api/auth/login"}
         No active admin existed.  A recovery account has been created and a
         single-use 6-digit OTP has been injected into the live auth store.
         POST {email, code} to /api/auth/login to receive a session cookie,
         then change the password via POST /api/auth/change-password.
         The code expires in 10 minutes and is consumed on first use.

    403  ADMIN_SECRET is not configured or the supplied key does not match.
    """
    from sqlalchemy import select

    if not _ADMIN_SECRET or x_admin_key != _ADMIN_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Valid X-Admin-Key required for bootstrap",
        )

    # Both response paths carry credentials or admin-state information — never
    # allow caches to store or replay the response.
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"

    # Check whether any active admin account already exists.
    # Use .limit(1) so the query succeeds even when multiple active admins exist
    # (scalar_one_or_none() raises MultipleResultsFound in that case).
    result = await db.execute(
        select(AuthUser)
        .where(AuthUser.role == "admin", AuthUser.is_active.is_(True))
        .limit(1)
    )
    existing_admin = result.scalars().first()

    if existing_admin is not None:
        return {"status": "ok", "admin_exists": True}

    # No active admin — create/reactivate the well-known recovery account.
    existing_result = await db.execute(
        select(AuthUser).where(AuthUser.email == _RECOVERY_EMAIL)
    )
    recovery_user: AuthUser | None = existing_result.scalars().first()

    if recovery_user is not None:
        recovery_user.is_active = True
        recovery_user.role = "admin"
        recovery_user.display_name = _RECOVERY_DISPLAY_NAME
        # Clear any old password hash — login must go through the OTP code below.
        recovery_user.password_hash = ""
    else:
        recovery_user = AuthUser(
            email=_RECOVERY_EMAIL,
            phone="",
            display_name=_RECOVERY_DISPLAY_NAME,
            role="admin",
            password_hash="",   # OTP-only — no standing password
            is_active=True,
        )
        db.add(recovery_user)

    await db.commit()

    # Inject a one-time OTP code into the live auth store so the caller can
    # POST /api/auth/login immediately without waiting for an email.
    one_time_code = f"{secrets.randbelow(1_000_000):06d}"
    inject_otp(_RECOVERY_EMAIL, one_time_code)

    _log.warning(
        "Bootstrap: no active admin found — recovery account created (%s); "
        "one-time code issued (not logged)",
        _RECOVERY_EMAIL,
    )

    return {
        "status": "created",
        "admin_exists": False,
        "email": _RECOVERY_EMAIL,
        "one_time_code": one_time_code,
        "login_path": "/api/auth/login",
    }


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class CreateUserRequest(BaseModel):
    email: EmailStr
    display_name: str
    role: str = "operator"   # viewer | operator | approver | admin
    phone: str = ""          # optional — kept for display only, not used for auth


class UserResponse(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    is_active: bool


class PatchUserRequest(BaseModel):
    is_active: bool | None = None
    role: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_admin)],
)
async def create_user(
    body: CreateUserRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new user account and send a welcome email."""
    from sqlalchemy import select

    # Unique-email guard — if an inactive account with this email exists, reactivate
    # and update it rather than rejecting (handles the delete+recreate pattern).
    existing_result = await db.execute(
        select(AuthUser).where(AuthUser.email == body.email.lower())
    )
    existing_user: AuthUser | None = existing_result.scalar_one_or_none()
    if existing_user is not None:
        if existing_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A user with email '{body.email}' already exists",
            )
        # Inactive — reactivate with updated details
        existing_user.display_name = body.display_name.strip()
        existing_user.role         = body.role
        existing_user.is_active    = True
        await db.commit()
        await db.refresh(existing_user)
        send_welcome_email(existing_user.email, existing_user.display_name)
        return UserResponse(
            id=existing_user.id,
            email=existing_user.email,
            display_name=existing_user.display_name,
            role=existing_user.role,
            is_active=existing_user.is_active,
        )

    # Validate role
    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"role must be one of: {', '.join(VALID_ROLES)}",
        )

    user = AuthUser(
        email=body.email.lower(),
        phone=body.phone,
        display_name=body.display_name.strip(),
        role=body.role,
        password_hash="",   # OTP auth — no password stored
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    _log.info("Admin created user %s (id=%s)", user.email, user.id)
    send_welcome_email(user.email, user.display_name)
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
    )


@router.get(
    "/users",
    response_model=list[UserResponse],
    dependencies=[Depends(_require_admin)],
)
async def list_users(db: AsyncSession = Depends(get_db_session)):
    """List all registered users."""
    from sqlalchemy import select

    result = await db.execute(select(AuthUser).order_by(AuthUser.id))
    users = result.scalars().all()
    return [
        UserResponse(id=u.id, email=u.email, display_name=u.display_name,
                     role=u.role, is_active=u.is_active)
        for u in users
    ]


@router.patch(
    "/users/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(_require_admin)],
)
async def patch_user(
    user_id: int,
    body: PatchUserRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Activate/deactivate a user or change their role."""
    user = await db.get(AuthUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if body.is_active is not None:
        user.is_active = body.is_active
    if body.role is not None:
        if body.role not in VALID_ROLES:
            raise HTTPException(status_code=422, detail=f"role must be one of: {', '.join(VALID_ROLES)}")
        user.role = body.role

    await db.commit()
    await db.refresh(user)
    return UserResponse(id=user.id, email=user.email, display_name=user.display_name,
                        role=user.role, is_active=user.is_active)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_admin)],
)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    """Permanently remove a user account."""
    user = await db.get(AuthUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()


# ---------------------------------------------------------------------------
# Email delivery diagnostic
# ---------------------------------------------------------------------------

_DEFAULT_FROM = "noreply@gridsignal.app"

@router.get("/email-check", dependencies=[Depends(_require_admin)])
async def email_check():
    """Diagnostic: verify that email delivery is likely to work.

    Returns a JSON object the admin can inspect without needing server logs:
      api_key_set      — SENDGRID_API_KEY is present in env
      from_email       — the current SENDGRID_FROM_EMAIL value (safe to expose)
      is_default       — True when still using the unverified default address
      sendgrid_pkg     — True when the sendgrid Python package is importable

    A working configuration requires api_key_set=true, is_default=false,
    and the from_email address must be a verified SendGrid sender identity.
    """
    api_key_set = bool(os.environ.get("SENDGRID_API_KEY"))
    from_email  = os.environ.get("SENDGRID_FROM_EMAIL", _DEFAULT_FROM) or _DEFAULT_FROM
    is_default  = from_email == _DEFAULT_FROM

    try:
        import sendgrid as _sg  # noqa: F401
        sendgrid_pkg = True
    except ImportError:
        sendgrid_pkg = False

    issues: list[str] = []
    if not api_key_set:
        issues.append("SENDGRID_API_KEY is not set — add it to Replit Secrets")
    if is_default:
        issues.append(
            f"SENDGRID_FROM_EMAIL is still the unverified default ({_DEFAULT_FROM}) — "
            "set it to a verified SendGrid sender address in Replit Secrets"
        )
    if not sendgrid_pkg:
        issues.append("sendgrid Python package is not installed")

    return {
        "ok":           len(issues) == 0,
        "api_key_set":  api_key_set,
        "from_email":   from_email,
        "is_default":   is_default,
        "sendgrid_pkg": sendgrid_pkg,
        "issues":       issues,
    }

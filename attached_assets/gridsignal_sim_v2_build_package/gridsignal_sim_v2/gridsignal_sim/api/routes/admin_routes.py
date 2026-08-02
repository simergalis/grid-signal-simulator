"""
api/routes/admin_routes.py — Admin-only user management endpoints.

Access is granted by either:
  • X-Admin-Key header matching ADMIN_SECRET (curl / server-side callers), or
  • A valid session cookie with role="admin" (browser admin page).

If ADMIN_SECRET is not set the header path is disabled, but session-based
admin access still works for users whose role is "admin".

POST   /api/admin/users           — create a user account; sends welcome email
GET    /api/admin/users           — list all users
PATCH  /api/admin/users/{user_id} — activate / deactivate an account or change role
DELETE /api/admin/users/{user_id} — permanently delete an account

The admin never sets a password directly.  Instead, provide a
`temporary_password` in the create request; the user receives it via the
welcome email and should change it on first login.
"""
from __future__ import annotations

import logging
import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import hash_password, COOKIE_NAME, decode_access_token
from api.db import get_db_session
from api.email_service import send_welcome_email
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
# Pydantic schemas
# ---------------------------------------------------------------------------

class CreateUserRequest(BaseModel):
    # Field accepted as "password" in the API body (was "temporary_password" —
    # renamed so the standard curl / UI payload is intuitive).
    email: EmailStr
    phone: str           # mobile phone number — required credential
    display_name: str
    role: str = "operator"   # viewer | operator | approver
    password: str | None = None   # auto-generated if omitted


class UserResponse(BaseModel):
    id: int
    email: str
    phone: str
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
        # Inactive — reactivate with fresh credentials
        existing_user.phone        = body.phone.strip()
        existing_user.display_name = body.display_name.strip()
        existing_user.role         = body.role
        existing_user.password_hash = hash_password(body.password or secrets.token_urlsafe(12))
        existing_user.is_active    = True
        await db.commit()
        await db.refresh(existing_user)
        return UserResponse(
            id=existing_user.id,
            email=existing_user.email,
            phone=existing_user.phone,
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

    tmp_pw = body.password or secrets.token_urlsafe(12)

    user = AuthUser(
        email=body.email.lower(),
        phone=body.phone.strip(),
        display_name=body.display_name.strip(),
        role=body.role,
        password_hash=hash_password(tmp_pw),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    email_sent = send_welcome_email(
        to_email=user.email,
        display_name=user.display_name,
        temporary_password=tmp_pw,
    )
    if not email_sent:
        _log.warning(
            "Welcome email could not be sent for %s — check SENDGRID_API_KEY "
            "and SENDGRID_FROM_EMAIL.  The account was created successfully.",
            user.email,
        )

    _log.info("Admin created user %s (id=%s, email_sent=%s)", user.email, user.id, email_sent)
    return UserResponse(
        id=user.id,
        email=user.email,
        phone=user.phone,
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
        UserResponse(
            id=u.id,
            email=u.email,
            phone=u.phone,
            display_name=u.display_name,
            role=u.role,
            is_active=u.is_active,
        )
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
    return UserResponse(
        id=user.id,
        email=user.email,
        phone=user.phone,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
    )


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

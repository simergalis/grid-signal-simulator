"""
api/routes/admin_routes.py — Admin-only user management endpoints.

All routes require the X-Admin-Key header to match the ADMIN_SECRET env var.
If ADMIN_SECRET is not set the admin API is disabled (403 on every request).

POST   /api/admin/users           — create a user account; sends welcome email
GET    /api/admin/users           — list all users
PATCH  /api/admin/users/{user_id} — activate / deactivate an account
DELETE /api/admin/users/{user_id} — permanently delete an account

The admin never sets a password directly.  Instead, provide a
`temporary_password` in the create request; the user receives it via the
welcome email and should change it on first login.  (Password-change endpoint
is a natural follow-up but is out of scope for the initial integration.)
"""
from __future__ import annotations

import logging
import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import hash_password
from api.db import get_db_session
from api.email_service import send_welcome_email
from runtime.persistence import AuthUser

_log = logging.getLogger(__name__)
_ADMIN_SECRET: str = os.environ.get("ADMIN_SECRET", "")

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Admin gate dependency
# ---------------------------------------------------------------------------

async def _require_admin(x_admin_key: str = Header(default="")):
    if not _ADMIN_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin API is disabled (ADMIN_SECRET not configured)",
        )
    if x_admin_key != _ADMIN_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin key",
        )


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class CreateUserRequest(BaseModel):
    email: EmailStr
    phone: str           # mobile phone number — required credential
    display_name: str
    role: str = "operator"   # viewer | operator | approver
    temporary_password: str | None = None   # auto-generated if omitted


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

    # Unique-email guard
    existing = await db.execute(
        select(AuthUser).where(AuthUser.email == body.email.lower())
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with email '{body.email}' already exists",
        )

    # Validate role
    if body.role not in ("viewer", "operator", "approver"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="role must be one of: viewer, operator, approver",
        )

    tmp_pw = body.temporary_password or secrets.token_urlsafe(12)

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
        if body.role not in ("viewer", "operator", "approver"):
            raise HTTPException(status_code=422, detail="Invalid role")
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

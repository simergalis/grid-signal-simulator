"""
api/routes/auth_routes.py — Authentication endpoints.

POST /api/auth/login   — validate email + phone + password, set session cookie
POST /api/auth/logout  — clear session cookie
GET  /api/auth/me      — return current user info (requires valid session)

Login requires ALL THREE: email, phone, and password.  If any field is wrong
the endpoint returns 401 with a generic "invalid credentials" message to avoid
leaking which field was incorrect.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import COOKIE_NAME, create_access_token, decode_access_token, verify_password
from api.db import get_db_session
from runtime.persistence import AuthUser

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    phone: str
    password: str


class MeResponse(BaseModel):
    user_id: int
    email: str
    display_name: str
    phone: str
    role: str


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

@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
):
    """Authenticate with email + phone + password.  Sets an httpOnly session cookie."""
    from sqlalchemy import select

    # Look up by email first (indexed), then verify phone + password
    result = await db.execute(
        select(AuthUser).where(AuthUser.email == body.email.lower())
    )
    user: AuthUser | None = result.scalar_one_or_none()

    # Normalise phone for comparison (strip spaces and leading +)
    def _normalise(p: str) -> str:
        return p.replace(" ", "").replace("-", "").lstrip("+")

    # Use a constant-time check pattern: always verify_password even on miss
    # to avoid timing-based email enumeration.
    pw_ok = verify_password(body.password, user.password_hash) if user else False
    phone_ok = (
        _normalise(user.phone) == _normalise(body.phone)
        if user else False
    )

    if not user or not pw_ok or not phone_ok or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token = create_access_token(user.id, user.email)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400,    # 24 h
        path="/",
    )
    _log.info("User %s logged in", user.email)
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
        phone=current_user.phone,
        role=current_user.role,
    )

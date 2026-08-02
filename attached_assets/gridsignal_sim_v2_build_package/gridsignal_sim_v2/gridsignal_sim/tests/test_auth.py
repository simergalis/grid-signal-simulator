"""
tests/test_auth.py — Security regression tests for the auth / admin layer.

Four assertions required by §Security:

  SEC-1  POST /api/auth/login with a wrong OTP code returns 401
  SEC-2  GET  /api/* (a protected endpoint) without a session cookie returns 401
  SEC-3  POST /api/admin/users without X-Admin-Key and without a session returns 403
  SEC-4  POST /api/admin/users with a valid session whose role is "operator"
         (not "admin") returns 403

Design notes
------------
The four tests are intentionally sync (no @pytest.mark.asyncio) so they can
use FastAPI's synchronous TestClient, which is the pattern used throughout
this test suite.  DB setup for SEC-4 uses asyncio.run() which works safely
here because sync test functions run in the main thread without a live event
loop — no conflict with TestClient's internal anyio thread.

All tests create a fresh app instance via create_app() so they share the
module-level SQLite DB file but start with a clean RunManager and lifespan.
Auth tables are guaranteed to exist: TestClient's __enter__ triggers the
app lifespan, which calls create_auth_tables().
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from api.app import create_app
from api.auth_utils import COOKIE_NAME, create_access_token
from api.db import _SessionLocal, create_auth_tables
from api.routes.auth_routes import inject_otp
from runtime.persistence import AuthUser


# ---------------------------------------------------------------------------
# Internal helper — insert (or reset) a test user directly in the shared DB
# ---------------------------------------------------------------------------

async def _ensure_user(email: str, role: str) -> int:
    """Upsert a user account in the shared DB and return its id.

    Calling create_auth_tables() before this ensures the auth_user table
    exists even if no TestClient lifespan has run yet.
    """
    from sqlalchemy import select

    async with _SessionLocal() as session:
        result = await session.execute(
            select(AuthUser).where(AuthUser.email == email)
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = AuthUser(
                email=email,
                phone="",
                display_name=f"Test {role.capitalize()}",
                role=role,
                password_hash="",
                is_active=True,
            )
            session.add(user)
        else:
            # Reset to the desired state in case a previous run left stale data.
            user.role = role
            user.is_active = True
        await session.commit()
        await session.refresh(user)
        return user.id


# ---------------------------------------------------------------------------
# SEC-1 — wrong OTP code → 401
# ---------------------------------------------------------------------------

def test_login_wrong_code_returns_401() -> None:
    """POST /api/auth/login with an invalid code must return 401, not 200 or 500."""
    # Inject a known OTP for a test address, then send a different code.
    inject_otp("sec1-test@example.com", "111111")
    with TestClient(create_app()) as client:
        resp = client.post(
            "/api/auth/login",
            json={"email": "sec1-test@example.com", "code": "000000"},
        )
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# SEC-2 — no session cookie → 401 on a protected /api/ path
# ---------------------------------------------------------------------------

def test_protected_api_without_cookie_returns_401() -> None:
    """GET /api/fabric/fixture without a session cookie must return 401.

    /api/fabric/fixture is a real endpoint protected by the auth middleware
    (it is not in the /api/auth/, /api/admin, /api/solar/, /api/location,
    or /api/session/ pass-through groups).
    """
    with TestClient(create_app()) as client:
        resp = client.get("/api/fabric/fixture")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# SEC-3 — no X-Admin-Key, no session → 403 on admin endpoint
# ---------------------------------------------------------------------------

def test_admin_endpoint_without_credentials_returns_403() -> None:
    """POST /api/admin/users without any credentials must return 403, not 200."""
    with TestClient(create_app()) as client:
        resp = client.post(
            "/api/admin/users",
            json={
                "email": "sec3-target@example.com",
                "display_name": "Target",
                "role": "viewer",
            },
        )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# SEC-4 — valid session with role="operator" → 403 on admin endpoint
# ---------------------------------------------------------------------------

def test_admin_endpoint_with_operator_session_returns_403() -> None:
    """POST /api/admin/users with an operator-role session must return 403.

    Strategy
    --------
    1. Ensure the auth_user table exists (asyncio.run → create_auth_tables).
    2. Upsert a test operator account directly in the DB (asyncio.run →
       _ensure_user).  This avoids the bootstrap/email flow entirely.
    3. Mint a valid JWT for that user via create_access_token — the same
       function used by the real login route — so the cookie is
       cryptographically indistinguishable from a genuine session.
    4. POST /api/admin/users with that cookie.  _require_admin() will decode
       the JWT, look up the user, find role="operator" (≠ "admin"), and
       raise HTTP 403.
    """
    # Step 1: ensure auth tables exist before any direct DB write.
    asyncio.run(create_auth_tables())

    # Step 2: ensure the operator account exists and is active.
    op_email = "sec4-operator@example.com"
    user_id = asyncio.run(_ensure_user(op_email, "operator"))

    # Step 3: mint a valid operator JWT (no DB call needed here).
    token = create_access_token(user_id, op_email)

    # Step 4: call an admin endpoint with the operator session.
    with TestClient(create_app()) as client:
        resp = client.post(
            "/api/admin/users",
            json={
                "email": "sec4-target@example.com",
                "display_name": "Target",
                "role": "viewer",
            },
            cookies={COOKIE_NAME: token},
        )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"

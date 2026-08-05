"""
tests/test_auth.py — Security regression tests for the auth / admin layer.

Assertions covered:

  SEC-1  POST /api/auth/login with a wrong OTP code returns 401
  SEC-2  GET  /api/* (a protected endpoint) without a session cookie returns 401
  SEC-3  POST /api/admin/users without X-Admin-Key and without a session returns 403
  SEC-4  POST /api/admin/users with a valid session whose role is "operator"
         (not "admin") returns 403

  PW-1   POST /api/auth/change-password with no prior password (first-time set)
         succeeds — current_password is not required when password_hash is empty.
  PW-2   POST /api/auth/change-password with the correct current password succeeds
         and the session cookie remains valid after the change.
  PW-3   POST /api/auth/change-password with a wrong current password returns 401.

Design notes
------------
SEC-1 through SEC-4 are synchronous tests that use FastAPI's TestClient.
PW-1 through PW-3 are async tests (pytest.mark.asyncio) that use an isolated
in-memory SQLite database injected via dependency_overrides, following the
same pattern as TC-B7 in test_bootstrap.py.  This avoids the event-loop
teardown issues that arise when asyncpg connection pools are closed inside a
sync test's anyio thread.
"""

from __future__ import annotations

import asyncio

import pytest
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


# ---------------------------------------------------------------------------
# Shared helper for PW tests — isolated SQLite engine + session factory
# ---------------------------------------------------------------------------

async def _make_sqlite_engine():
    """Return a fresh in-memory SQLite async engine with all auth tables created."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from runtime.persistence import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        bind=engine, expire_on_commit=False, class_=AsyncSession
    )
    return engine, session_factory


async def _insert_user(session_factory, email: str, password_hash: str = "") -> int:
    """Insert a minimal active operator user and return its id."""
    from sqlalchemy.ext.asyncio import AsyncSession

    async with session_factory() as session:
        user = AuthUser(
            email=email,
            phone="",
            display_name="Test Operator",
            role="operator",
            password_hash=password_hash,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


# ---------------------------------------------------------------------------
# PW-1 — first-time password set (no prior password_hash) succeeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_change_password_first_time_set_succeeds() -> None:
    """POST /api/auth/change-password succeeds when password_hash is empty.

    Strategy
    --------
    1. Insert a user with password_hash="" using an isolated in-memory SQLite DB.
    2. Override get_db_session with a real session from that engine.
    3. Mint a valid JWT for the user (no email round-trip needed).
    4. POST /api/auth/change-password without current_password — not required
       on the first-time path.
    5. Expect 200 {"ok": true}.
    6. Confirm the session cookie is still accepted by GET /api/auth/me.

    Uses httpx.AsyncClient + ASGITransport (native async, no anyio bridge) so
    the test shares the pytest-asyncio event loop without spawning a second one.
    """
    import httpx
    from api.db import get_db_session

    engine, session_factory = await _make_sqlite_engine()

    pw1_email = "pw1-firstset@example.com"
    user_id = await _insert_user(session_factory, pw1_email, password_hash="")

    async def _real_db():
        async with session_factory() as session:
            yield session

    token = create_access_token(user_id, pw1_email)

    app = create_app()
    app.dependency_overrides[get_db_session] = _real_db

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # PW-1: first-time set — no current_password needed.
        resp = await client.post(
            "/api/auth/change-password",
            json={"new_password": "FirstPass1!"},
            cookies={COOKIE_NAME: token},
        )
        assert resp.status_code == 200, (
            f"PW-1 expected 200 on first-time set, got {resp.status_code}: {resp.text}"
        )
        assert resp.json().get("ok") is True, f"PW-1 body not ok: {resp.json()}"

        # Session cookie must still be valid after the password change.
        me_resp = await client.get(
            "/api/auth/me",
            cookies={COOKIE_NAME: token},
        )
        assert me_resp.status_code == 200, (
            f"PW-1 session invalid after password set: {me_resp.status_code}: {me_resp.text}"
        )

    await engine.dispose()


# ---------------------------------------------------------------------------
# PW-2 — subsequent change with correct current password succeeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_change_password_correct_current_password_succeeds() -> None:
    """POST /api/auth/change-password succeeds when current password matches.

    Strategy
    --------
    1. Insert a user with a known bcrypt password_hash.
    2. Override get_db_session with a real SQLite session.
    3. POST /api/auth/change-password supplying the correct current_password.
    4. Expect 200 {"ok": true}.
    5. Confirm the session cookie is still valid after the change.

    Uses httpx.AsyncClient + ASGITransport (native async, no anyio bridge).
    """
    import httpx
    from api.auth_utils import hash_password
    from api.db import get_db_session

    engine, session_factory = await _make_sqlite_engine()

    pw2_email = "pw2-subsequent@example.com"
    user_id = await _insert_user(
        session_factory, pw2_email, password_hash=hash_password("InitialPass1!")
    )

    async def _real_db():
        async with session_factory() as session:
            yield session

    token = create_access_token(user_id, pw2_email)

    app = create_app()
    app.dependency_overrides[get_db_session] = _real_db

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "InitialPass1!",
                "new_password": "UpdatedPass2!",
            },
            cookies={COOKIE_NAME: token},
        )
        assert resp.status_code == 200, (
            f"PW-2 expected 200 on correct current password, got {resp.status_code}: {resp.text}"
        )
        assert resp.json().get("ok") is True, f"PW-2 body not ok: {resp.json()}"

        # Session cookie must still be valid after the password change.
        me_resp = await client.get(
            "/api/auth/me",
            cookies={COOKIE_NAME: token},
        )
        assert me_resp.status_code == 200, (
            f"PW-2 session invalid after password change: {me_resp.status_code}: {me_resp.text}"
        )

    await engine.dispose()


# ---------------------------------------------------------------------------
# PW-3 — wrong current password is rejected with 401
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_change_password_wrong_current_password_returns_401() -> None:
    """POST /api/auth/change-password returns 401 when current password is wrong.

    Strategy
    --------
    1. Insert a user with a known bcrypt password_hash.
    2. Override get_db_session with a real SQLite session.
    3. POST /api/auth/change-password with an incorrect current_password.
    4. Expect 401 — the password must NOT be changed.

    Uses httpx.AsyncClient + ASGITransport (native async, no anyio bridge).
    """
    import httpx
    from api.auth_utils import hash_password
    from api.db import get_db_session

    engine, session_factory = await _make_sqlite_engine()

    pw3_email = "pw3-wrongpw@example.com"
    user_id = await _insert_user(
        session_factory, pw3_email, password_hash=hash_password("CorrectPass1!")
    )

    async def _real_db():
        async with session_factory() as session:
            yield session

    token = create_access_token(user_id, pw3_email)

    app = create_app()
    app.dependency_overrides[get_db_session] = _real_db

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "WrongPass999!",
                "new_password": "NewPass3!",
            },
            cookies={COOKIE_NAME: token},
        )

    assert resp.status_code == 401, (
        f"PW-3 expected 401 for wrong current password, got {resp.status_code}: {resp.text}"
    )

    await engine.dispose()

"""
tests/test_bootstrap.py — Acceptance tests for GET /api/admin/bootstrap.

The bootstrap endpoint is the break-glass recovery path: when every admin
account has been deactivated or deleted it creates a recovery account and
injects a one-time OTP code directly into the live auth store so the caller
can POST /api/auth/login immediately without waiting for an email.

Unit tests (TC-B1 – TC-B6)
---------------------------
Fast mocked tests that verify the endpoint's HTTP contract without touching
a real database.

Integration test (TC-B7)
------------------------
Uses a real in-memory SQLite database (via SQLAlchemy async engine) injected
through FastAPI's dependency_overrides.  Exercises the full recovery round-
trip: bootstrap → /api/auth/login → /api/auth/me confirms admin session.

Isolation strategy
------------------
``_ADMIN_SECRET`` is a module-level constant read at import time; tests patch
it via ``monkeypatch.setattr``.  Unit tests override ``get_db_session`` with
an ``AsyncMock`` session.  The integration test creates a fresh in-memory
SQLite engine per test and overrides ``get_db_session`` with a real session
from that engine, keeping it completely isolated from the on-disk DB.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import api.routes.admin_routes as _ar
from api.app import create_app
from api.db import get_db_session
from runtime.persistence import AuthUser


_SECRET = "test-bootstrap-secret"


# ---------------------------------------------------------------------------
# Helpers — unit-test mocks
# ---------------------------------------------------------------------------

def _make_admin_mock(is_active: bool = True):
    """Minimal AuthUser stub — plain MagicMock to avoid SQLAlchemy ORM init."""
    u = MagicMock(spec=AuthUser)
    u.id = 1
    u.email = "admin@example.com"
    u.display_name = "Admin"
    u.role = "admin"
    u.is_active = is_active
    u.password_hash = ""
    u.phone = ""
    return u


def _db_override_first(first_result=None):
    """Return a FastAPI dependency that yields a mock AsyncSession.

    ``first_result`` is what ``scalars().first()`` returns for every
    ``db.execute(...)`` call — simulates a simple single-query path.
    """
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = first_result

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    async def _dep():
        yield mock_session

    return _dep


def _client_with_db(db_dep) -> TestClient:
    """Return a TestClient whose DB session is fully mocked."""
    app = create_app()
    app.dependency_overrides[get_db_session] = db_dep
    return TestClient(app)


def _bootstrap(client: TestClient, key: str = _SECRET):
    return client.get("/api/admin/bootstrap", headers={"X-Admin-Key": key})


# ---------------------------------------------------------------------------
# TC-B1  No admin key → 403
# ---------------------------------------------------------------------------

def test_bootstrap_no_key_is_forbidden(monkeypatch) -> None:
    monkeypatch.setattr(_ar, "_ADMIN_SECRET", _SECRET)
    with _client_with_db(_db_override_first(first_result=None)) as client:
        resp = client.get("/api/admin/bootstrap")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TC-B2  Wrong admin key → 403
# ---------------------------------------------------------------------------

def test_bootstrap_wrong_key_is_forbidden(monkeypatch) -> None:
    monkeypatch.setattr(_ar, "_ADMIN_SECRET", _SECRET)
    with _client_with_db(_db_override_first(first_result=None)) as client:
        resp = _bootstrap(client, key="not-the-right-key")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TC-B3  Active admin exists → 200, status=ok, no credentials leaked
# ---------------------------------------------------------------------------

def test_bootstrap_when_admin_exists_returns_ok(monkeypatch) -> None:
    monkeypatch.setattr(_ar, "_ADMIN_SECRET", _SECRET)
    active_admin = _make_admin_mock(is_active=True)
    with _client_with_db(_db_override_first(first_result=active_admin)) as client:
        resp = _bootstrap(client)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["admin_exists"] is True
    assert "one_time_code" not in body
    assert "email" not in body
    # Response must never be cached — even the "no action" path discloses admin state.
    assert "no-store" in resp.headers.get("cache-control", "")
    assert "private" in resp.headers.get("cache-control", "")


# ---------------------------------------------------------------------------
# TC-B4  Multiple active admins → 200, status=ok (no MultipleResultsFound)
# ---------------------------------------------------------------------------

def test_bootstrap_multiple_admins_returns_ok(monkeypatch) -> None:
    """The existence query uses .limit(1) so two active admins don't raise."""
    monkeypatch.setattr(_ar, "_ADMIN_SECRET", _SECRET)
    # Even with multiple rows the query returns the first one — mock that.
    active_admin = _make_admin_mock(is_active=True)
    with _client_with_db(_db_override_first(first_result=active_admin)) as client:
        resp = _bootstrap(client)

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# TC-B5  No active admin → 200, status=created, one_time_code returned
# ---------------------------------------------------------------------------

def test_bootstrap_creates_recovery_when_no_admin(monkeypatch) -> None:
    monkeypatch.setattr(_ar, "_ADMIN_SECRET", _SECRET)
    # Both the "find active admin" and "find existing recovery email" queries
    # return None, so a brand-new recovery account must be created.
    with _client_with_db(_db_override_first(first_result=None)) as client:
        resp = _bootstrap(client)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "created"
    assert body["admin_exists"] is False
    assert "email" in body
    assert "one_time_code" in body
    assert len(body["one_time_code"]) == 6
    assert body["one_time_code"].isdigit()
    assert "login_path" in body
    assert "temporary_password" not in body
    # Credential in response — must never be cached.
    assert "no-store" in resp.headers.get("cache-control", "")
    assert "private" in resp.headers.get("cache-control", "")


# ---------------------------------------------------------------------------
# TC-B6  Deactivated admin only → creates recovery account
# ---------------------------------------------------------------------------

def test_bootstrap_deactivated_admin_triggers_recovery(monkeypatch) -> None:
    """The query filters on is_active=True, so an inactive admin returns None."""
    monkeypatch.setattr(_ar, "_ADMIN_SECRET", _SECRET)
    with _client_with_db(_db_override_first(first_result=None)) as client:
        resp = _bootstrap(client)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "created"
    assert body["admin_exists"] is False
    assert "one_time_code" in body


# ---------------------------------------------------------------------------
# TC-B7  Integration: bootstrap → login → /me confirms admin session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bootstrap_one_time_code_is_usable_for_login(monkeypatch) -> None:
    """End-to-end recovery round-trip using a real in-memory SQLite database.

    1. Call GET /api/admin/bootstrap with a valid admin key.
    2. Confirm a recovery account is reported as created and a 6-digit code
       is returned.
    3. POST /api/auth/login with that email + code.
    4. GET /api/auth/me to confirm the session cookie grants admin access.
    """
    from sqlalchemy import text
    from runtime.persistence import Base

    monkeypatch.setattr(_ar, "_ADMIN_SECRET", _SECRET)

    # Build a fresh in-memory SQLite engine with all tables created.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(
        bind=engine, expire_on_commit=False, class_=AsyncSession
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Override get_db_session with a real session from our isolated engine.
    async def _real_db():
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = _real_db

    with TestClient(app) as client:
        # Step 1: bootstrap — no admins exist yet.
        boot_resp = _bootstrap(client)
        assert boot_resp.status_code == 200, boot_resp.text
        boot_body = boot_resp.json()
        assert boot_body["status"] == "created"
        assert boot_body["admin_exists"] is False

        email = boot_body["email"]
        code  = boot_body["one_time_code"]

        # Step 2: login with the returned one-time code.
        login_resp = client.post(
            "/api/auth/login",
            json={"email": email, "code": code},
        )
        assert login_resp.status_code == 200, login_resp.text
        assert login_resp.json()["role"] == "admin"
        assert "gs_session" in login_resp.cookies

        # Step 3: /me confirms the session is valid and role is admin.
        me_resp = client.get(
            "/api/auth/me",
            cookies={"gs_session": login_resp.cookies["gs_session"]},
        )
        assert me_resp.status_code == 200, me_resp.text
        me_body = me_resp.json()
        assert me_body["role"] == "admin"
        assert me_body["email"] == email

    await engine.dispose()

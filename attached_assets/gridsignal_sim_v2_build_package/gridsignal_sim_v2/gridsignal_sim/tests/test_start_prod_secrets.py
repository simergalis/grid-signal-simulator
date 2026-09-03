"""Acceptance tests for production startup secret policy."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


START_PROD = (
    Path(__file__).resolve().parents[1] / "scripts" / "start_prod.sh"
)


def _check_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("JWT_SECRET", None)
    env.pop("SESSION_SECRET", None)
    env.pop("MISTRAL_API_KEY", None)
    env.pop("ANTHROPIC_API_KEY", None)
    env["GRIDSIGNAL_STARTUP_CHECK_ONLY"] = "1"
    return env


def test_startup_check_rejects_missing_auth_secret() -> None:
    result = subprocess.run(
        ["bash", str(START_PROD), "--check-secrets"],
        env=_check_env(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "production startup blocked" in output
    assert "JWT_SECRET" in output
    assert "SESSION_SECRET" in output


def test_startup_check_allows_optional_ai_secrets_to_be_absent() -> None:
    env = _check_env()
    env["SESSION_SECRET"] = "acceptance-test-secret"

    result = subprocess.run(
        ["bash", str(START_PROD), "--check-secrets"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    output = (result.stdout + result.stderr).lower()
    assert "mistral_api_key" in output
    assert "anthropic_api_key" in output
    assert "optional" in output


def test_startup_check_rejects_missing_production_email_credentials() -> None:
    env = _check_env()
    env["SESSION_SECRET"] = "acceptance-test-secret"
    env.pop("SENDGRID_API_KEY", None)
    env.pop("SENDGRID_FROM_EMAIL", None)

    result = subprocess.run(
        ["bash", str(START_PROD), "--check-secrets"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "production startup blocked" in output
    assert "SENDGRID_API_KEY" in output
    assert "SENDGRID_FROM_EMAIL" in output
"""
api/email_service.py — SendGrid transactional email helpers.

Two emails are sent:
  welcome_email  — when the admin creates a new user account.
  password_reset — (future; placeholder for extension).

SENDGRID_API_KEY must be set in Replit Secrets.  If the key is absent the
send functions log a warning and return False rather than raising, so a
missing key is never a hard startup failure (LP-1 pattern from §8.1).

SENDGRID_FROM_EMAIL env var sets the verified sender address.  Defaults to
"noreply@gridsignal.app" — this must match a SendGrid verified sender identity
before emails will actually deliver.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

_log = logging.getLogger(__name__)

_APP_NAME: str = "GridSignal Simulator"


def _api_key() -> Optional[str]:
    """Read SENDGRID_API_KEY fresh each call so secrets added after startup work."""
    return os.environ.get("SENDGRID_API_KEY") or None


def _from_email() -> str:
    """Read SENDGRID_FROM_EMAIL fresh each call so secrets added after startup work."""
    return os.environ.get("SENDGRID_FROM_EMAIL", "noreply@gridsignal.app")


def _portal_url() -> str:
    """
    Resolve the public URL of the GridSignal portal for use in emails.

    Defaults to https://gridsgnl.com.  Set APP_PORTAL_URL in Replit Secrets
    to override (e.g. for a staging environment).  REPLIT_DEV_DOMAIN is
    intentionally ignored — it is the internal dev tunnel, not the public URL.
    """
    explicit = os.environ.get("APP_PORTAL_URL", "").strip()
    return explicit.rstrip("/") if explicit else "https://app.gridsgnl.com"


def _get_client():
    key = _api_key()
    if not key:
        return None
    try:
        from sendgrid import SendGridAPIClient
        return SendGridAPIClient(key)
    except ImportError:
        _log.warning("sendgrid package not installed — email delivery disabled")
        return None


def send_welcome_email(to_email: str, display_name: str) -> bool:
    """
    Send a welcome email to a newly created user explaining the OTP sign-in flow.

    Returns True on success, False if delivery failed or is not configured.
    No password is included — users sign in with their email and a one-time code.
    """
    client = _get_client()
    if not client:
        _log.warning(
            "SENDGRID_API_KEY not set — welcome email NOT sent to %s", to_email
        )
        return False

    url    = _portal_url()
    sender = _from_email()
    subject = f"Welcome to {_APP_NAME}"
    body = f"""\
<div style="font-family:sans-serif;max-width:480px;margin:0 auto;background:#0b1017;color:#e6ecf2;padding:40px 32px;border-radius:8px">

  <!-- Header -->
  <p style="color:#3fb6a8;font-size:22px;font-weight:700;letter-spacing:0.12em;margin:0 0 2px">GRIDSIGNAL</p>
  <p style="color:#4b5764;font-size:12px;margin:0 0 24px">Predictive power management</p>
  <hr style="border:none;border-top:1px solid #1e2a38;margin:0 0 28px">

  <!-- Greeting -->
  <p style="margin:0 0 16px">Hi {display_name},</p>
  <p style="margin:0 0 16px">
    Welcome to GridSignal. Your account is ready and you can sign in right now
    — no password required.
  </p>

  <!-- Login email callout -->
  <div style="background:#111821;border-left:3px solid #3fb6a8;border-radius:0 6px 6px 0;padding:14px 18px;margin:0 0 20px">
    <p style="color:#7d8b9c;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;margin:0 0 4px">Your sign-in email</p>
    <p style="font-family:monospace;font-size:15px;color:#e6ecf2;margin:0">{to_email}</p>
  </div>

  <!-- How to sign in -->
  <p style="margin:0 0 8px;font-weight:600;color:#c8d6e5">How to sign in</p>
  <ol style="margin:0 0 24px;padding-left:20px;line-height:1.8;color:#c8d6e5">
    <li>Go to <a href="{url}" style="color:#3fb6a8;text-decoration:none">{url}</a></li>
    <li>Enter your email address above</li>
    <li>Check your inbox for a 6-digit code and enter it</li>
  </ol>

  <!-- CTA -->
  <div style="text-align:center;margin:32px 0 28px">
    <a href="{url}"
       style="display:inline-block;background:#3fb6a8;color:#0b1017;font-weight:700;
              font-size:15px;text-decoration:none;padding:14px 36px;border-radius:6px;
              letter-spacing:0.04em">
      Open GridSignal
    </a>
  </div>

  <hr style="border:none;border-top:1px solid #1e2a38;margin:0 0 20px">

  <p style="color:#7d8b9c;font-size:12px;margin:0">
    If you weren't expecting this invitation, you can safely ignore this email.
    Your account will remain inactive until you first sign in.
  </p>
</div>
"""
    try:
        from sendgrid.helpers.mail import Mail
        message = Mail(
            from_email=sender,
            to_emails=to_email,
            subject=subject,
            html_content=body,
        )
        resp = client.send(message)
        success = 200 <= resp.status_code < 300
        if success:
            _log.info("Welcome email sent to %s (status=%s)", to_email, resp.status_code)
        else:
            try:
                body_text = resp.body.decode() if isinstance(resp.body, (bytes, bytearray)) else str(resp.body)
            except Exception:
                body_text = "<unreadable>"
            _log.warning(
                "SendGrid returned status %s for welcome email to %s — body: %s",
                resp.status_code, to_email, body_text,
            )
        return success
    except Exception as exc:  # noqa: BLE001
        _log.error("Failed to send welcome email to %s: %s", to_email, exc)
        return False


def send_otp_email(to_email: str, display_name: str, code: str) -> bool:
    """
    Send a 6-digit sign-in code to the user.

    Returns True on success, False if delivery failed or is not configured.
    """
    client = _get_client()
    if not client:
        _log.warning("SENDGRID_API_KEY not set — OTP email NOT sent to %s", to_email)
        return False

    subject = f"{_APP_NAME} — your sign-in code"
    body = f"""\
<div style="font-family:sans-serif;max-width:480px;margin:0 auto;background:#0b1017;color:#e6ecf2;padding:32px;border-radius:8px">
  <p style="color:#3fb6a8;font-size:20px;font-weight:700;letter-spacing:0.1em;margin-bottom:4px">GRIDSIGNAL</p>
  <p style="color:#4b5764;font-size:12px;margin-top:0">Predictive power management</p>
  <hr style="border:none;border-top:1px solid #1e2a38;margin:20px 0">
  <p>Hello {display_name},</p>
  <p>Your sign-in code is:</p>
  <div style="font-size:36px;font-weight:700;letter-spacing:0.2em;color:#3fb6a8;
              background:#111821;border-radius:6px;padding:16px 24px;
              text-align:center;margin:20px 0">{code}</div>
  <p style="color:#7d8b9c;font-size:12px">
    This code expires in 10 minutes and can only be used once.<br>
    If you did not request this code, ignore this email.
  </p>
</div>
"""
    try:
        from sendgrid.helpers.mail import Mail
        message = Mail(
            from_email=_from_email(),
            to_emails=to_email,
            subject=subject,
            html_content=body,
        )
        resp = client.send(message)
        success = 200 <= resp.status_code < 300
        if success:
            _log.info("OTP email sent to %s (status=%s)", to_email, resp.status_code)
        else:
            # Log the response body so operators can diagnose "unverified sender" (403),
            # "invalid API key" (401), or domain-authentication failures from server logs.
            try:
                body_text = resp.body.decode() if isinstance(resp.body, (bytes, bytearray)) else str(resp.body)
            except Exception:
                body_text = "<unreadable>"
            _log.warning(
                "SendGrid returned status %s for OTP to %s — body: %s",
                resp.status_code, to_email, body_text,
            )
        return success
    except Exception as exc:  # noqa: BLE001
        _log.error("Failed to send OTP email to %s: %s", to_email, exc)
        return False


def send_password_reset_email(to_email: str, reset_token: str, base_url: str) -> bool:
    """
    Send a password-reset link.  Placeholder — not wired to a reset flow yet.
    """
    client = _get_client()
    if not client:
        _log.warning("SENDGRID_API_KEY not set — reset email NOT sent to %s", to_email)
        return False

    reset_url = f"{base_url}/reset-password?token={reset_token}"
    subject = f"{_APP_NAME} — password reset request"
    body = f"""\
<p>A password reset was requested for your {_APP_NAME} account.</p>
<p><a href="{reset_url}">Click here to reset your password</a></p>
<p>This link expires in 1 hour.  If you did not request a reset, ignore this email.</p>
"""
    try:
        from sendgrid.helpers.mail import Mail
        message = Mail(
            from_email=_from_email(),
            to_emails=to_email,
            subject=subject,
            html_content=body,
        )
        resp = client.send(message)
        return 200 <= resp.status_code < 300
    except Exception as exc:  # noqa: BLE001
        _log.error("Failed to send reset email to %s: %s", to_email, exc)
        return False

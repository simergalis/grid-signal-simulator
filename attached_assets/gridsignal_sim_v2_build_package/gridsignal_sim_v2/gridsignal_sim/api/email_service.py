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
<div style="font-family:sans-serif;max-width:500px;margin:0 auto;background:#0b1017;color:#e6ecf2;border-radius:10px;overflow:hidden">
  <!-- Top accent bar -->
  <div style="background:#3fb6a8;height:4px;line-height:4px;font-size:0">&nbsp;</div>
  <!-- Header -->
  <div style="padding:36px 36px 0">
    <p style="margin:0 0 3px;color:#3fb6a8;font-size:22px;font-weight:700;letter-spacing:0.12em">GRIDSIGNAL</p>
    <p style="margin:0;color:#8a97a6;font-size:12px;letter-spacing:0.02em">Predictive power management</p>
  </div>
  <!-- Divider -->
  <div style="padding:24px 36px 0"><div style="border-top:1px solid #1e2a38"></div></div>
  <!-- Body -->
  <div style="padding:28px 36px 0">
    <p style="margin:0 0 16px;font-size:15px;line-height:1.65">
      Hi <strong>{display_name}</strong>,
    </p>
    <p style="margin:0 0 16px;font-size:15px;line-height:1.65;color:#c8d6e5">
      Your GridSignal account is ready. GridSignal reads job-scheduler
      activity to forecast power demand 30&ndash;60 seconds ahead, so
      generators, batteries, and cooling stage before a load spike
      instead of chasing it.
    </p>
    <p style="margin:0 0 24px;font-size:15px;line-height:1.65;color:#c8d6e5">
      There's no password to create. Every sign-in uses a one-time
      code sent to your email.
    </p>
    <!-- Sign-in email callout -->
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
           style="background:#111821;border-left:3px solid #3fb6a8;margin-bottom:26px">
      <tr><td style="padding:14px 18px">
        <p style="margin:0 0 6px;color:#8a97a6;font-size:11px;text-transform:uppercase;letter-spacing:0.08em">
          Sign in with this address
        </p>
        <p style="margin:0;font-family:monospace;font-size:15px;color:#e6ecf2">{to_email}</p>
      </td></tr>
    </table>
    <!-- How to sign in -->
    <p style="margin:0 0 12px;font-size:14px;font-weight:600;color:#e6ecf2;letter-spacing:0.02em">How to sign in</p>
    <table cellpadding="0" cellspacing="0" role="presentation" style="margin-bottom:28px">
      <tr>
        <td style="padding:5px 0;vertical-align:top">
          <span style="display:inline-block;width:22px;height:22px;background:#1e2a38;border-radius:50%;text-align:center;line-height:22px;font-size:12px;font-weight:700;color:#3fb6a8;margin-right:12px">1</span>
        </td>
        <td style="padding:5px 0;font-size:14px;color:#c8d6e5;line-height:1.6;vertical-align:top">
          Go to <a href="{url}" style="color:#3fb6a8;text-decoration:none">app.gridsgnl.com</a>
        </td>
      </tr>
      <tr>
        <td style="padding:5px 0;vertical-align:top">
          <span style="display:inline-block;width:22px;height:22px;background:#1e2a38;border-radius:50%;text-align:center;line-height:22px;font-size:12px;font-weight:700;color:#3fb6a8;margin-right:12px">2</span>
        </td>
        <td style="padding:5px 0;font-size:14px;color:#c8d6e5;line-height:1.6;vertical-align:top">
          Enter the address above
        </td>
      </tr>
      <tr>
        <td style="padding:5px 0;vertical-align:top">
          <span style="display:inline-block;width:22px;height:22px;background:#1e2a38;border-radius:50%;text-align:center;line-height:22px;font-size:12px;font-weight:700;color:#3fb6a8;margin-right:12px">3</span>
        </td>
        <td style="padding:5px 0;font-size:14px;color:#c8d6e5;line-height:1.6;vertical-align:top">
          We'll send a 6-digit code in a <span style="color:#e6ecf2">separate email</span>.
          Enter it to finish. Codes expire after 10 minutes.
        </td>
      </tr>
    </table>
    <!-- CTA button -->
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="margin-bottom:32px">
      <tr><td align="center">
        <a href="{url}"
           style="display:inline-block;background:#3fb6a8;color:#0b1017;font-weight:700;
                  font-size:15px;text-decoration:none;padding:14px 40px;
                  border-radius:6px;letter-spacing:0.04em">
          Open GridSignal
        </a>
      </td></tr>
    </table>
  </div>
  <!-- Divider -->
  <div style="padding:0 36px"><div style="border-top:1px solid #1e2a38"></div></div>
  <!-- Footer -->
  <div style="padding:20px 36px 36px">
    <p style="margin:0 0 10px;color:#8a97a6;font-size:12px;line-height:1.6">
      Trouble signing in? Reply to this email and we'll sort it out.
    </p>
    <p style="margin:0;color:#8a97a6;font-size:12px;line-height:1.6">
      Didn't expect this invitation? You can ignore this email. The
      account stays inactive until someone signs in for the first time.
    </p>
  </div>
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

"""
Email service. Active only when SMTP_* env vars are set (no secrets committed):
  SMTP_HOST, SMTP_FROM  (required)   SMTP_PORT (default 587)  SMTP_USER / SMTP_PASS (optional)
When unconfigured, send_email() is a safe no-op returning False, so the app works
end-to-end in dev without email (reminders still appear in-app; reset tokens are
returned in the dev response).
"""
import os
import logging
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def email_enabled() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))


def send_email(to_addr: str, subject: str, body: str) -> bool:
    if not (email_enabled() and to_addr):
        return False
    try:
        msg = EmailMessage()
        msg["From"] = os.getenv("SMTP_FROM")
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content(body)
        host = os.getenv("SMTP_HOST")
        port = int(os.getenv("SMTP_PORT", "587"))
        user = os.getenv("SMTP_USER", "")
        pwd = os.getenv("SMTP_PASS", "")
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            if user:
                s.login(user, pwd)
            s.send_message(msg)
        return True
    except Exception as e:
        logger.warning(f"Email send failed: {e}")
        return False

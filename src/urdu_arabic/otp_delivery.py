"""Real OTP delivery: email via Gmail SMTP, WhatsApp via Twilio's REST API.

Both are optional and independently configured (see Settings in
src/settings.py) -- whichever channel matches the identifier's shape
(email vs phone number) is used, and if its credentials aren't set, or
the send itself fails, this logs the code instead of raising, so local
dev and a misconfigured deployment both keep working exactly like the
original log-only placeholder did.

Gmail SMTP setup (one-time, in the Google account that will send the
mail):
  1. Turn on 2-Step Verification: myaccount.google.com/security
  2. Create an App Password: myaccount.google.com/apppasswords
     (pick "Mail" as the app -- Gmail no longer accepts your normal
     account password for SMTP).
  3. Set env vars: URDU_ARABIC_SMTP_USER=you@gmail.com
                   URDU_ARABIC_SMTP_APP_PASSWORD=<the 16-char app password>
  Gmail's free SMTP relay has a ~500 messages/day cap -- fine for OTPs at
  this scale, but not a bulk-mail provider.

Twilio WhatsApp setup:
  1. Create a Twilio account: twilio.com -- the console gives you an
     Account SID and Auth Token immediately.
  2. For testing: join the shared sandbox (console -> Messaging -> Try it
     out -> Send a WhatsApp message) by sending the shown "join <word>"
     code from each test recipient's WhatsApp to the sandbox number --
     the default URDU_ARABIC_TWILIO_WHATSAPP_FROM already points at it.
  3. For production: register your own WhatsApp sender number with Twilio
     (needs Meta Business verification) and set
     URDU_ARABIC_TWILIO_WHATSAPP_FROM to "whatsapp:+<that number>".
  4. Set env vars: URDU_ARABIC_TWILIO_ACCOUNT_SID, URDU_ARABIC_TWILIO_AUTH_TOKEN
  Recipient phone numbers (the `identifier` users log in with) must be in
  E.164 form (e.g. +923001234567) for Twilio to accept them.
"""

from __future__ import annotations

import logging
import re
import smtplib
from email.mime.text import MIMEText

import httpx

from src.settings import get_settings

logger = logging.getLogger("urdu_arabic.otp_delivery")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_email(identifier: str) -> bool:
    return bool(_EMAIL_RE.match(identifier))


def _log_fallback(identifier: str, code: str) -> None:
    logger.info("OTP for %s: %s", identifier, code)


def _send_email(to_email: str, code: str) -> bool:
    settings = get_settings()
    if not (settings.urdu_arabic_smtp_user and settings.urdu_arabic_smtp_app_password):
        return False

    message = MIMEText(f"Your Lisan verification code is: {code}\n\nIt expires in a few minutes.")
    message["Subject"] = f"Your Lisan verification code: {code}"
    message["From"] = f"{settings.urdu_arabic_otp_email_from_name} <{settings.urdu_arabic_smtp_user}>"
    message["To"] = to_email

    try:
        with smtplib.SMTP(settings.urdu_arabic_smtp_host, settings.urdu_arabic_smtp_port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(settings.urdu_arabic_smtp_user, settings.urdu_arabic_smtp_app_password)
            smtp.sendmail(settings.urdu_arabic_smtp_user, [to_email], message.as_string())
        return True
    except Exception:
        logger.exception("Failed to send OTP email to %s, falling back to log", to_email)
        return False


def _send_whatsapp(to_phone: str, code: str) -> bool:
    settings = get_settings()
    if not (settings.urdu_arabic_twilio_account_sid and settings.urdu_arabic_twilio_auth_token):
        return False

    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.urdu_arabic_twilio_account_sid}/Messages.json"
    try:
        response = httpx.post(
            url,
            auth=(settings.urdu_arabic_twilio_account_sid, settings.urdu_arabic_twilio_auth_token),
            data={
                "From": settings.urdu_arabic_twilio_whatsapp_from,
                "To": f"whatsapp:{to_phone}",
                "Body": f"Your Lisan verification code is: {code}",
            },
            timeout=10,
        )
        response.raise_for_status()
        return True
    except Exception:
        logger.exception("Failed to send OTP WhatsApp message to %s, falling back to log", to_phone)
        return False


def send_otp(identifier: str, code: str) -> None:
    sent = _send_email(identifier, code) if is_email(identifier) else _send_whatsapp(identifier, code)
    if not sent:
        _log_fallback(identifier, code)

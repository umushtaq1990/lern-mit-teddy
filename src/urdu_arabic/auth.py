"""Lightweight OTP login, isolated from src.frontend.auth's Entra/CIAM flow.

A mass consumer audience in Pakistan/India doesn't fit an enterprise CIAM
tenant -- this is a self-contained phone-or-email + one-time-code flow
instead, with its own session cookie (separate secret from the existing
frontend's SessionMiddleware).

Real delivery (Gmail SMTP for an email identifier, Twilio WhatsApp for a
phone one) lives in otp_delivery.py -- see its module docstring for setup.
That module itself falls back to logging the code if its credentials
aren't configured, so this keeps working unchanged in local dev.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from src.db.session import get_session_factory
from src.settings import get_settings

from .events import log_event
from .models import UrduArabicOtpCode, UrduArabicUser
from .otp_delivery import send_otp

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


class RequestOtpBody(BaseModel):
    identifier: str  # phone number or email


class VerifyOtpBody(BaseModel):
    identifier: str
    code: str


@dataclass(frozen=True)
class AuthUser:
    user_id: int
    identifier: str


@router.post("/request-otp")
def request_otp(body: RequestOtpBody) -> dict[str, str]:
    identifier = body.identifier.strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="identifier is required")

    code = f"{secrets.randbelow(1_000_000):06d}"
    ttl = get_settings().urdu_arabic_otp_ttl_seconds
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

    db = get_session_factory()()
    try:
        db.add(UrduArabicOtpCode(identifier=identifier, code_hash=_hash_code(code), expires_at=expires_at))
        db.commit()
    finally:
        db.close()

    send_otp(identifier, code)
    return {"status": "sent"}


@router.post("/verify-otp")
def verify_otp(body: VerifyOtpBody, request: Request) -> dict[str, str]:
    identifier = body.identifier.strip()
    code = body.code.strip()

    db = get_session_factory()()
    try:
        now = datetime.now(timezone.utc)
        otp = db.scalars(
            select(UrduArabicOtpCode)
            .where(
                UrduArabicOtpCode.identifier == identifier,
                UrduArabicOtpCode.code_hash == _hash_code(code),
                UrduArabicOtpCode.consumed_at.is_(None),
                UrduArabicOtpCode.expires_at > now,
            )
            .order_by(UrduArabicOtpCode.created_at.desc())
        ).first()
        if otp is None:
            raise HTTPException(status_code=400, detail="Invalid or expired code")

        otp.consumed_at = now

        user = db.scalars(select(UrduArabicUser).where(UrduArabicUser.identifier == identifier)).first()
        if user is None:
            user = UrduArabicUser(identifier=identifier)
            db.add(user)
            db.flush()

        db.commit()
        request.session["user"] = {"user_id": user.id, "identifier": user.identifier}
        log_event(user.id, "login")
        return {"status": "ok"}
    finally:
        db.close()


@router.post("/logout")
def logout(request: Request) -> dict[str, str]:
    user = request.session.get("user")
    if user:
        log_event(user["user_id"], "logout")
    request.session.pop("user", None)
    return {"status": "ok"}


def current_user(request: Request) -> AuthUser | None:
    data = request.session.get("user")
    if not data:
        return None
    return AuthUser(user_id=data["user_id"], identifier=data["identifier"])

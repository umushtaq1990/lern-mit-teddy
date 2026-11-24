"""Small upsert helpers for live user/session tracking.

Query-then-insert-or-update rather than a dialect-specific `ON CONFLICT` —
keeps identical behavior across Postgres (docker-compose) and SQLite (tests),
which matters more here than upsert throughput (this app writes one row per
login and one row per call, not a high-volume path).

Every function here is best-effort: a DB write failure must never break the
live request (login / call start) it's attached to — it's tracking, not a
critical dependency — so callers get a bool back and failures are logged,
not raised. This also means the app degrades gracefully if DATABASE_URL
points at a database that isn't reachable yet (e.g. in an environment where
Postgres hasn't been provisioned as a follow-on step).
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session as SqlAlchemySession

from .models import Session, User

logger = logging.getLogger(__name__)


def upsert_user(db: SqlAlchemySession, *, user_id: str, display_name: str, email: str | None = None) -> bool:
    try:
        user = db.get(User, user_id)
        if user is None:
            db.add(User(user_id=user_id, display_name=display_name, email=email))
        else:
            user.display_name = display_name
            if email is not None:
                user.email = email
        db.commit()
        return True
    except Exception:
        logger.warning("upsert_user failed for user_id=%s", user_id, exc_info=True)
        db.rollback()
        return False


def upsert_session(
    db: SqlAlchemySession,
    *,
    session_id: str,
    user_id: str | None = None,
    room: str | None = None,
    language: str | None = None,
    native_language: str | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    llm_model: str | None = None,
    stt_model: str | None = None,
    tts_model: str | None = None,
) -> bool:
    try:
        row = db.get(Session, session_id)
        if row is None:
            row = Session(session_id=session_id)
            db.add(row)
        if user_id is not None:
            row.user_id = user_id
        if room is not None:
            row.room = room
        if language is not None:
            row.language = language
        if native_language is not None:
            row.native_language = native_language
        if started_at is not None:
            row.started_at = started_at
        if ended_at is not None:
            row.ended_at = ended_at
        if llm_model is not None:
            row.llm_model = llm_model
        if stt_model is not None:
            row.stt_model = stt_model
        if tts_model is not None:
            row.tts_model = tts_model
        db.commit()
        return True
    except Exception:
        logger.warning("upsert_session failed for session_id=%s", session_id, exc_info=True)
        db.rollback()
        return False

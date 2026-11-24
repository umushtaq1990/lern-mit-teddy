"""Repository upsert tests against in-memory SQLite — no Postgres required."""

from __future__ import annotations

from datetime import datetime, timezone

from src.db.models import Session, User
from src.db.repository import upsert_session, upsert_user


def test_upsert_user_creates_then_updates(sqlite_session):
    ok = upsert_user(sqlite_session, user_id="u1", display_name="Sam", email="sam@example.com")
    assert ok is True

    row = sqlite_session.get(User, "u1")
    assert row.display_name == "Sam"
    assert row.email == "sam@example.com"

    upsert_user(sqlite_session, user_id="u1", display_name="Samuel")
    sqlite_session.refresh(row)
    assert row.display_name == "Samuel"
    assert row.email == "sam@example.com"  # unchanged: email=None means "don't touch"


def test_upsert_session_creates_then_updates(sqlite_session):
    started = datetime.now(timezone.utc)
    upsert_user(sqlite_session, user_id="u1", display_name="Sam")

    ok = upsert_session(
        sqlite_session,
        session_id="s1",
        user_id="u1",
        room="room-1",
        language="de",
        native_language="en",
        started_at=started,
    )
    assert ok is True

    row = sqlite_session.get(Session, "s1")
    assert row.user_id == "u1"
    assert row.room == "room-1"
    assert row.ended_at is None

    ended = datetime.now(timezone.utc)
    upsert_session(sqlite_session, session_id="s1", ended_at=ended)
    sqlite_session.refresh(row)
    assert row.ended_at is not None
    # Fields not passed on the second call are left untouched.
    assert row.room == "room-1"


def test_upsert_session_without_user_id_is_allowed(sqlite_session):
    """Sessions can exist before/without a resolved user (defensive — the live
    app always has a logged-in user, but this must not crash if ever absent)."""
    ok = upsert_session(sqlite_session, session_id="s2", room="room-2")
    assert ok is True
    row = sqlite_session.get(Session, "s2")
    assert row.user_id is None

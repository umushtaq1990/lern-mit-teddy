"""Behavioral-event logging, isolated behind one function so every call
site (server endpoints, auth, frontend-driven /api/events calls) writes the
same shape of row -- a single `urdu_arabic_events` table, queryable later
for behavioral analysis / Grafana without having to reconcile different
schemas per event type.
"""

from __future__ import annotations

import json
from typing import Any

from src.db.session import get_session_factory

from .models import UrduArabicEvent


def log_event(
    user_id: int | None,
    event_type: str,
    lesson_id: str | None = None,
    part_id: str | None = None,
    language: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    db = get_session_factory()()
    try:
        db.add(
            UrduArabicEvent(
                user_id=user_id,
                event_type=event_type,
                lesson_id=lesson_id,
                part_id=part_id,
                language=language,
                metadata_json=json.dumps(metadata) if metadata else None,
            )
        )
        db.commit()
    finally:
        db.close()

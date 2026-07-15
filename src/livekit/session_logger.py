"""Local per-session conversation logs — JSONL, one line per turn.

Separate from LangSmith/Langfuse cloud tracing: this is a local, always-on
fallback so any session's conversation can be reviewed directly from disk,
without cloud dashboard access and without depending on the in-memory
LangGraph checkpoint (which is lost whenever the worker process restarts).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs" / "sessions"


def _safe_filename(session_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", session_id) or "unknown"


class SessionLogger:
    """Appends one JSON line per turn to logs/sessions/<session_id>.jsonl."""

    def __init__(self, session_id: str, *, language: str, native_language: str, room: str = ""):
        self._path = LOG_DIR / f"{_safe_filename(session_id)}.jsonl"
        self._language = language
        self._native_language = native_language
        self._room = room
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            logger.warning("Could not create session log directory", exc_info=True)

    def log(self, role: str, text: str, **extra) -> None:
        """role: 'user' | 'assistant' | 'translation' | 'system'."""
        if not text:
            return
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "room": self._room,
            "language": self._language,
            "native_language": self._native_language,
            "role": role,
            "text": text,
            **extra,
        }
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            logger.warning("Failed to write session log entry", exc_info=True)

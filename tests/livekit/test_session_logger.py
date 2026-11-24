"""SessionLogger is a zero-dependency module — no env vars, no network,
no other src/ imports — so this is a pure filesystem test."""

from __future__ import annotations

import json

from src.livekit import session_logger


def test_log_writes_one_jsonl_line_per_turn(tmp_path, monkeypatch):
    monkeypatch.setattr(session_logger, "LOG_DIR", tmp_path)

    logger = session_logger.SessionLogger("room-1", language="de", native_language="en", room="room-1")
    logger.log("user", "Hallo")
    logger.log("assistant", "Hallo! Wie geht's?")

    log_file = tmp_path / "room-1.jsonl"
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    first = json.loads(lines[0])
    assert first["role"] == "user"
    assert first["text"] == "Hallo"
    assert first["language"] == "de"
    assert first["native_language"] == "en"


def test_log_skips_empty_text(tmp_path, monkeypatch):
    monkeypatch.setattr(session_logger, "LOG_DIR", tmp_path)

    logger = session_logger.SessionLogger("room-2", language="en", native_language="en")
    logger.log("user", "")

    assert not (tmp_path / "room-2.jsonl").exists()


def test_session_id_sanitized_for_filesystem(tmp_path, monkeypatch):
    monkeypatch.setattr(session_logger, "LOG_DIR", tmp_path)

    logger = session_logger.SessionLogger("weird/id:with*chars", language="en", native_language="en")
    logger.log("user", "hi")

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    assert "/" not in files[0].name

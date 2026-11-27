"""Standalone async worker: polls urdu_arabic_questions for pending rows and
answers them. Run directly: `python -m src.urdu_arabic.worker`.

Uses `SELECT ... FOR UPDATE SKIP LOCKED` (Postgres-native) instead of
Redis/Celery -- consistent with this repo's existing "no Redis" stance, and
proportionate since this is a single-worker, low-volume MVP queue.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select  # noqa: E402

from src.db.session import get_session_factory  # noqa: E402

from . import content, llm, stt, storage, tts  # noqa: E402
from .languages import DEFAULT_LANGUAGE  # noqa: E402
from .models import UrduArabicQuestion  # noqa: E402

logger = logging.getLogger("urdu_arabic.worker")

POLL_INTERVAL_SECONDS = 3


def _claim_next_question(db) -> UrduArabicQuestion | None:
    row = db.scalars(
        select(UrduArabicQuestion)
        .where(UrduArabicQuestion.status == "pending")
        .order_by(UrduArabicQuestion.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if row is not None:
        row.status = "processing"
        db.commit()
    return row


def _process_question(row: UrduArabicQuestion) -> None:
    language = row.language or DEFAULT_LANGUAGE
    question_text = row.question_text
    if not question_text and row.question_audio_path:
        question_text = stt.transcribe(row.question_audio_path, language=language)

    if not question_text:
        raise ValueError("No question text available after transcription")

    lesson_context = content.get_part_context(row.lesson_id, row.part_id, language=language)
    generation = llm.answer_question(question_text, lesson_context, language=language)
    answer_text = generation.text

    # The text answer is the useful part; audio is a nice-to-have on top of
    # it. Don't lose an already-generated answer just because TTS (an
    # external, flakier dependency) failed -- degrade to text-only instead.
    answer_audio_path: str | None = None
    try:
        audio_bytes = tts.synthesize(answer_text, language=language)
        answer_audio_path = storage.save_bytes(audio_bytes, subdir="answers", suffix=".mp3")
    except Exception:
        logger.warning("TTS failed for question id=%s, answering with text only", row.id, exc_info=True)

    row.question_text = question_text  # persist the transcript too
    row.answer_text = answer_text
    row.answer_audio_path = answer_audio_path
    row.status = "answered"
    row.answered_at = datetime.now(timezone.utc)
    row.llm_latency_ms = generation.latency_ms
    row.prompt_tokens = generation.prompt_tokens
    row.completion_tokens = generation.completion_tokens


def run_once() -> bool:
    """Process one pending question, if any. Returns True if one was processed."""
    db = get_session_factory()()
    try:
        row = _claim_next_question(db)
        if row is None:
            return False

        try:
            _process_question(row)
            db.commit()
            logger.info("Answered question id=%s", row.id)
        except Exception as exc:
            logger.exception("Failed to answer question id=%s", row.id)
            db.rollback()
            row = db.get(UrduArabicQuestion, row.id)
            if row is not None:
                row.status = "failed"
                row.error = str(exc)
                db.commit()
        return True
    finally:
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("Urdu/Arabic worker starting, polling every %ss...", POLL_INTERVAL_SECONDS)
    while True:
        processed = run_once()
        if not processed:
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

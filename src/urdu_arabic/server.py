"""Standalone FastAPI app for the Urdu/Arabic learning app.

Run directly: `python -m src.urdu_arabic.server`. Deliberately does not
import anything from src.livekit or src.frontend -- this is a separate,
isolated module (see src/urdu_arabic/__init__.py).
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()  # must run before src.settings reads the environment

from fastapi import FastAPI, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402


class NoCacheStaticFiles(StaticFiles):
    """This content is actively edited during development (frontend files,
    and generated lesson audio/images regenerated under the same filename)
    -- plain StaticFiles lets browsers skip revalidation entirely via
    heuristic caching, which repeatedly caused a changed app.js/style.css
    or a regenerated example image to keep showing stale content until an
    explicit hard refresh. Forcing revalidation on every request still lets
    the browser reuse its cached copy via a cheap 304 when nothing changed,
    it just guarantees a real change is never silently skipped."""

    def file_response(self, *args, **kwargs):  # noqa: ANN002, ANN003
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response
from prometheus_fastapi_instrumentator import Instrumentator  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlalchemy import select  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from src.db.session import get_session_factory  # noqa: E402
from src.settings import get_settings  # noqa: E402

from . import auth, content, storage  # noqa: E402
from .events import log_event  # noqa: E402
from .languages import LANGUAGES  # noqa: E402
from .models import UrduArabicFeedback, UrduArabicQuestion  # noqa: E402

logging.getLogger("urdu_arabic").setLevel(logging.INFO)
if not logging.getLogger("urdu_arabic").handlers:
    logging.getLogger("urdu_arabic").addHandler(logging.StreamHandler())
request_logger = logging.getLogger("urdu_arabic.request")

STATIC_DIR = Path(__file__).resolve().parent / "static"
_settings = get_settings()

app = FastAPI(
    title="Urdu-Arabic Learning App",
    description="Isolated async Q&A app for Urdu-speaking Arabic learners",
    version="0.1.0",
)
app.add_middleware(
    SessionMiddleware,
    secret_key=_settings.urdu_arabic_session_secret,
    max_age=30 * 24 * 3600,
    same_site="lax",
    https_only=False,
)
app.include_router(auth.router)


def add_request_logging(app: FastAPI, service_name: str) -> None:
    """Ported from the JME reference architecture's request-logging pattern
    (app/common/request_logging.py): X-Request-ID + method/path/status/duration."""

    @app.middleware("http")
    async def _log_requests(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        request_logger.info(
            "[%s] %s %s -> %s (%sms)",
            service_name, request.method, request.url.path, response.status_code, duration_ms,
            extra={"request_id": request_id},
        )
        return response


add_request_logging(app, "urdu-arabic")
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/me")
def me(request: Request) -> dict[str, Any]:
    user = auth.current_user(request)
    if user is None:
        return {"user": None}
    return {"user": {"user_id": user.user_id, "identifier": user.identifier}}


@app.get("/api/languages")
def list_languages() -> dict[str, Any]:
    return {
        "languages": [
            {"code": code, "label": meta["label"], "dir": meta["dir"]}
            for code, meta in LANGUAGES.items()
        ]
    }


class EventBody(BaseModel):
    event_type: str
    lesson_id: str | None = None
    part_id: str | None = None
    language: str | None = None
    metadata: dict[str, Any] | None = None


@app.post("/api/events")
def record_event(body: EventBody, request: Request) -> dict[str, str]:
    """Client-driven behavioral events (lesson opened, part viewed, audio
    played, language switched, ...) that only the frontend observes --
    server-originated events (login/logout, questions, feedback) are logged
    directly at their own call sites instead of round-tripping here."""
    user = auth.current_user(request)
    log_event(
        user.user_id if user else None,
        body.event_type,
        lesson_id=body.lesson_id,
        part_id=body.part_id,
        language=body.language,
        metadata=body.metadata,
    )
    return {"status": "ok"}


class FeedbackBody(BaseModel):
    lesson_id: str
    part_id: str
    rating: str  # "up" | "down"


@app.post("/api/feedback")
def submit_feedback(body: FeedbackBody, request: Request) -> dict[str, str]:
    user = auth.current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Login required")
    if body.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'")

    db = get_session_factory()()
    try:
        row = db.scalars(
            select(UrduArabicFeedback).where(
                UrduArabicFeedback.user_id == user.user_id,
                UrduArabicFeedback.lesson_id == body.lesson_id,
                UrduArabicFeedback.part_id == body.part_id,
            )
        ).first()
        if row is None:
            row = UrduArabicFeedback(
                user_id=user.user_id, lesson_id=body.lesson_id, part_id=body.part_id, rating=body.rating
            )
            db.add(row)
        else:
            row.rating = body.rating
        db.commit()
    finally:
        db.close()

    log_event(user.user_id, "feedback_given", lesson_id=body.lesson_id, part_id=body.part_id, metadata={"rating": body.rating})
    return {"status": "ok"}


@app.get("/api/feedback")
def get_feedback(lesson_id: str, part_id: str, request: Request) -> dict[str, Any]:
    user = auth.current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Login required")

    db = get_session_factory()()
    try:
        row = db.scalars(
            select(UrduArabicFeedback).where(
                UrduArabicFeedback.user_id == user.user_id,
                UrduArabicFeedback.lesson_id == lesson_id,
                UrduArabicFeedback.part_id == part_id,
            )
        ).first()
        return {"rating": row.rating if row else None}
    finally:
        db.close()


@app.get("/api/lessons")
def list_lessons() -> dict[str, Any]:
    return {"lessons": content.list_lessons()}


@app.get("/api/lessons/{lesson_id}")
def get_lesson(lesson_id: str) -> dict[str, Any]:
    lesson = content.get_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson


@app.post("/api/questions")
async def submit_question(
    request: Request,
    lesson_id: str,
    part_id: str,
    text: str | None = None,
    audio: UploadFile | None = None,
    language: str = "ur",
) -> dict[str, int]:
    user = auth.current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Login required")
    if not text and audio is None:
        raise HTTPException(status_code=400, detail="Provide either text or audio")

    question_audio_path: str | None = None
    if audio is not None:
        data = await audio.read()
        suffix = Path(audio.filename or "question.wav").suffix or ".wav"
        question_audio_path = storage.save_bytes(data, subdir="questions", suffix=suffix)

    db = get_session_factory()()
    try:
        row = UrduArabicQuestion(
            user_id=user.user_id,
            lesson_id=lesson_id,
            part_id=part_id,
            language=language if language in LANGUAGES else "ur",
            question_text=text,
            question_audio_path=question_audio_path,
            status="pending",
        )
        db.add(row)
        db.commit()
        log_event(
            user.user_id,
            "question_asked",
            lesson_id=lesson_id,
            part_id=part_id,
            language=row.language,
            metadata={"has_audio": question_audio_path is not None, "has_text": bool(text)},
        )
        return {"id": row.id}
    finally:
        db.close()


@app.get("/api/questions")
def list_questions(
    request: Request, lesson_id: str | None = None, part_id: str | None = None
) -> dict[str, Any]:
    user = auth.current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Login required")

    db = get_session_factory()()
    try:
        filters = [UrduArabicQuestion.user_id == user.user_id]
        if lesson_id is not None:
            filters.append(UrduArabicQuestion.lesson_id == lesson_id)
        if part_id is not None:
            filters.append(UrduArabicQuestion.part_id == part_id)
        rows = db.scalars(
            select(UrduArabicQuestion).where(*filters).order_by(UrduArabicQuestion.created_at)
        ).all()
        return {
            "questions": [
                {
                    "id": row.id,
                    "lesson_id": row.lesson_id,
                    "part_id": row.part_id,
                    "language": row.language,
                    "status": row.status,
                    "question_text": row.question_text,
                    "question_audio_url": f"/api/questions/{row.id}/question-audio" if row.question_audio_path else None,
                    "answer_text": row.answer_text,
                    "answer_audio_url": f"/api/questions/{row.id}/audio" if row.answer_audio_path else None,
                    "error": row.error,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "answered_at": row.answered_at.isoformat() if row.answered_at else None,
                }
                for row in rows
            ]
        }
    finally:
        db.close()


@app.get("/api/questions/{question_id}/question-audio")
def get_question_question_audio(question_id: int, request: Request):
    from fastapi.responses import Response  # noqa: PLC0415

    user = auth.current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Login required")

    db = get_session_factory()()
    try:
        row = db.get(UrduArabicQuestion, question_id)
        if row is None or row.user_id != user.user_id or not row.question_audio_path:
            raise HTTPException(status_code=404, detail="Audio not found")
        data = storage.read_bytes(row.question_audio_path)
        return Response(content=data, media_type="audio/webm")
    finally:
        db.close()


@app.get("/api/questions/{question_id}")
def get_question(question_id: int, request: Request) -> dict[str, Any]:
    user = auth.current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Login required")

    db = get_session_factory()()
    try:
        row = db.get(UrduArabicQuestion, question_id)
        if row is None or row.user_id != user.user_id:
            raise HTTPException(status_code=404, detail="Question not found")
        return {
            "id": row.id,
            "status": row.status,
            "answer_text": row.answer_text,
            "answer_audio_url": f"/api/questions/{row.id}/audio" if row.answer_audio_path else None,
            "error": row.error,
        }
    finally:
        db.close()


@app.get("/api/questions/{question_id}/audio")
def get_question_audio(question_id: int, request: Request):
    from fastapi.responses import Response  # noqa: PLC0415

    user = auth.current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Login required")

    db = get_session_factory()()
    try:
        row = db.get(UrduArabicQuestion, question_id)
        if row is None or row.user_id != user.user_id or not row.answer_audio_path:
            raise HTTPException(status_code=404, detail="Audio not found")
        data = storage.read_bytes(row.answer_audio_path)
        return Response(content=data, media_type="audio/mpeg")
    finally:
        db.close()


if content.CONTENT_DATA_DIR.exists():
    app.mount("/content", NoCacheStaticFiles(directory=str(content.CONTENT_DATA_DIR)), name="content")

app.mount("/", NoCacheStaticFiles(directory=str(STATIC_DIR), html=True), name="static")


def main() -> None:
    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        "src.urdu_arabic.server:app",
        host=_settings.urdu_arabic_host,
        port=_settings.urdu_arabic_port,
        reload=True,
    )


if __name__ == "__main__":
    main()

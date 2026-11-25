"""SQLAlchemy models for the Urdu/Arabic learning app.

Registered on the SAME declarative `Base` as src/db/models.py (one shared
Postgres instance, one Alembic history) but with their own table names —
isolation here means a separate Python module and a separate login/identity
space, not a separate database.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models import Base


class UrduArabicUser(Base):
    __tablename__ = "urdu_arabic_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    identifier: Mapped[str] = mapped_column(String(320), unique=True)  # phone or email
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UrduArabicOtpCode(Base):
    __tablename__ = "urdu_arabic_otp_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    identifier: Mapped[str] = mapped_column(String(320))
    code_hash: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UrduArabicQuestion(Base):
    __tablename__ = "urdu_arabic_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("urdu_arabic_users.id"), nullable=True
    )
    lesson_id: Mapped[str] = mapped_column(String(100))
    part_id: Mapped[str] = mapped_column(String(100))
    language: Mapped[str] = mapped_column(String(10), default="ur", server_default="ur")
    question_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_audio_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|processing|answered|failed
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_audio_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UrduArabicEvent(Base):
    """Generic behavioral-analytics event log -- one row per user action
    (login, lesson opened, part viewed, audio played, language switched,
    chat message sent, ...). Deliberately schema-light (a free-form
    event_type string + optional lesson/part/language + a JSON metadata
    blob) so new event types never need a migration, just a new call site."""

    __tablename__ = "urdu_arabic_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("urdu_arabic_users.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50))
    lesson_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    part_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UrduArabicFeedback(Base):
    """One thumbs up/down per (user, lesson, part) -- re-rating the same
    part overwrites the previous value rather than piling up rows."""

    __tablename__ = "urdu_arabic_feedback"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id", "part_id", name="uq_urdu_arabic_feedback_user_part"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("urdu_arabic_users.id"))
    lesson_id: Mapped[str] = mapped_column(String(100))
    part_id: Mapped[str] = mapped_column(String(100))
    rating: Mapped[str] = mapped_column(String(10))  # "up" | "down"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

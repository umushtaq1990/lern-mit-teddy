"""SQLAlchemy models for user/session tracking.

The `users`/`sessions`/`export_state` shape is ported directly from
`pipelines/langfuse_export/schema.sql` (the existing Azure SQL schema used by
the cloud batch export job) — same table/column names, so the batch job's
upsert can coexist with these live writes without a schema split. That job
targets Azure SQL via pymssql and is untouched by this module; this is a
separate (Postgres-first, local-and-future-cloud) schema for the live app.

`content_items` is new — scaffolding only (see src/langgraph/eval or a future
ingestion module) for the "upload video lectures and books later" goal; no
ingestion code reads from it yet.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(100), ForeignKey("users.user_id"), nullable=True)
    room: Mapped[str | None] = mapped_column(String(200), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    native_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    turn_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    langfuse_trace_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    blob_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    exported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Enrichment columns, populated later by the Langfuse export job.
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stt_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tts_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback_comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class ExportState(Base):
    __tablename__ = "export_state"

    job_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    last_run_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ContentItem(Base):
    """Scaffolding for future course content (video lectures, books, PDFs)
    staged in data/ — no ingestion pipeline reads/writes this yet."""

    __tablename__ = "content_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(20))  # "video" | "pdf" | "book"
    title: Mapped[str] = mapped_column(String(300))
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="staged")  # "staged" | "ingested"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

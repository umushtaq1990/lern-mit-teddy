"""Engine/session setup — parameterized by settings.database_url so the same
code works against Postgres (docker-compose) or SQLite (tests), per
src/db/models.Base metadata.
"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as SqlAlchemySession
from sqlalchemy.orm import sessionmaker

from src.settings import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[SqlAlchemySession]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Generator[SqlAlchemySession, None, None]:
    """FastAPI dependency: yields a session, closes it when the request ends."""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()

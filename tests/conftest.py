"""Shared pytest fixtures.

Convention for this test suite (see tests/README.md): mock all LLM/Langfuse
network calls, use in-memory SQLite for DB-touching tests, and never require
docker-compose to be running — reserve that for tests/e2e (marked `e2e`).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.models import Base
from src.langgraph.agent import reset_agent_caches
from src.settings import get_settings


@pytest.fixture(autouse=True)
def reset_agent_state():
    """Clear the langgraph agent's process-global judge/word-attempt caches
    before and after every test, so one test's thread_id state can never
    leak into another's."""
    reset_agent_caches()
    yield
    reset_agent_caches()


@pytest.fixture
def test_settings(monkeypatch: pytest.MonkeyPatch):
    """Use inside a test to set env vars and get a freshly-constructed
    Settings object reflecting them:

        def test_something(test_settings):
            test_settings(AUTH_CLIENT_ID="abc", AUTH_TENANT_ID="def")
            ...

    Clears the get_settings() cache before and after so no state leaks
    between tests.
    """
    get_settings.cache_clear()

    def _apply(**env: str):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        return get_settings()

    yield _apply
    get_settings.cache_clear()


@pytest.fixture
def sqlite_session():
    """A fresh in-memory SQLite DB with all tables created, for DB-touching
    tests — no Postgres/docker-compose required."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()

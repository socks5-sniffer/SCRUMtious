"""Shared pytest fixtures.

Sets the required environment, isolates the session store on a temp directory,
and stubs out the heavy CrewAI orchestration so the HTTP layer can be tested
without the `crewai` dependency or live API calls.
"""

import os

import pytest

# Ensure required env exists before any app module is imported.
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("SESSION_LIST_TOKEN", "test-list-token")


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.security import rate_limit
    from app.services import crew_runner
    from app.services.session_store import store

    # Isolate persistence to a temp dir and start from an empty store.
    monkeypatch.setattr(store, "dir", tmp_path / "sessions")
    store.dir.mkdir(parents=True, exist_ok=True)
    store.sessions.clear()

    # Reset the process-wide rate limiter so tests don't interfere.
    rate_limit._run_rate_limit.clear()

    # Don't actually run CrewAI during tests.
    monkeypatch.setattr(crew_runner, "run_crew_sync", lambda *a, **k: None)

    from app.main import app

    return TestClient(app)

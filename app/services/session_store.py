"""In-memory session store with JSON-file persistence.

Sessions live in memory for the lifetime of the process and are mirrored to
``<SESSIONS_DIR>/<session_id>.json`` so completed runs survive a restart.
Transient, non-serialisable fields (the events queue and the HITL
``threading.Event``) are kept in memory only and reset on reload.

This is a single-process construct; see ``docs/architecture.md`` for the
tradeoffs and what multi-worker deployment would require.
"""

import json
import pathlib
from datetime import datetime, timezone
from typing import Any

from app.config import SESSIONS_DIR, logger


class SessionStore:
    """Holds the live session dictionary and handles disk persistence."""

    def __init__(self, sessions_dir: pathlib.Path) -> None:
        self.dir = sessions_dir
        self.dir.mkdir(exist_ok=True)
        self.sessions: dict[str, dict[str, Any]] = {}

    def path(self, session_id: str) -> pathlib.Path:
        return self.dir / f"{session_id}.json"

    def get(self, session_id: str) -> dict[str, Any] | None:
        return self.sessions.get(session_id)

    def __contains__(self, session_id: str) -> bool:
        return session_id in self.sessions

    def persist(self, session_id: str) -> None:
        """Write the session's serialisable state to disk."""
        session = self.sessions.get(session_id)
        if not session:
            return
        payload = {
            "session_id": session_id,
            "idea": session.get("idea", ""),
            "tech_stack": session.get("tech_stack", ""),
            "security_framework": session.get("security_framework", ""),
            "status": session.get("status", "running"),
            "created_at": session.get("created_at", datetime.now(timezone.utc).isoformat()),
            "outputs": session.get("outputs", {}),
            "verdict": session.get("verdict", ""),
            # HITL: which agent is awaiting approval right now
            "pending_approval": session.get("pending_approval", None),
        }
        try:
            self.path(session_id).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            logger.exception("Failed to persist session %s", session_id)

    def load_all(self) -> None:
        """Re-hydrate completed sessions from disk into memory on startup."""
        for p in self.dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                sid = data.get("session_id", p.stem)
                self.sessions[sid] = {
                    **data,
                    "events": [],
                    "_task_idx": 0,
                    "_hitl_event": None,  # not resumable after restart
                }
            except Exception:
                logger.warning("Could not load session file %s", p)


# Process-wide singleton shared by the API routes and the crew runner.
store = SessionStore(SESSIONS_DIR)

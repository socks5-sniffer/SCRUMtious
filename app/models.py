"""Domain models and metadata shared across the application.

Holds the canonical roster of Scrum agents used to render the UI, the Pydantic
request models for the API, and the typed shape of a session. Validation error
responses are normalised in ``app.main`` so the historical ``{"error": ...}``
contract and messages stay stable.
"""

import threading
from typing import Any, TypedDict

from pydantic import BaseModel, field_validator

# Input size limits (DoS / storage-growth mitigation).
MAX_IDEA_LENGTH = 2000
MAX_EDIT_LENGTH = 20000
# tech_stack / security_framework are short UI select values; cap them so they
# can't smuggle oversized text into session storage and agent prompts.
MAX_OPTION_LENGTH = 200


class RunRequest(BaseModel):
    """Body of ``POST /api/run``. Length/emptiness rules are enforced in the
    route handler to keep the exact historical error messages."""

    idea: str = ""
    tech_stack: str = ""
    security_framework: str = "OWASP Top-10"

    @field_validator("idea", "tech_stack", "security_framework")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class SessionState(TypedDict, total=False):
    """Shape of a session dict (in ``store.sessions``).

    Keys prefixed with ``_`` are transient: they never reach disk and are
    reset when a session is re-hydrated after a restart.
    """

    session_id: str
    status: str  # running | awaiting_approval | complete | error
    events: list[dict[str, Any]]
    idea: str
    tech_stack: str
    security_framework: str
    created_at: str
    outputs: dict[str, str]
    verdict: str
    pending_approval: str | None
    access_token: str
    _task_idx: int
    _hitl_event: threading.Event | None
    _hitl_edit: str | None
    _edited_agents: list[str]
    _hitl_timed_out: bool

# The ordered roster of agents shown in the UI and used to label outputs.
AGENTS: list[dict[str, Any]] = [
    {
        "id": "business_analyst",
        "role": "Business Analyst",
        "icon": "📋",
        "color": "#6366f1",
        "description": "Translates your idea into structured requirements with user stories, acceptance criteria, and edge cases.",
    },
    {
        "id": "product_owner",
        "role": "Product Owner",
        "icon": "🎯",
        "color": "#8b5cf6",
        "description": "Prioritises requirements and creates a sprint-ready backlog item with scope and definition of done.",
    },
    {
        "id": "lead_developer",
        "role": "Lead Developer",
        "icon": "⚡",
        "color": "#06b6d4",
        "description": "Implements secure code for your chosen tech stack, following the selected security framework with full input validation.",
    },
    {
        "id": "security_auditor",
        "role": "Security Auditor",
        "icon": "🛡️",
        "color": "#f59e0b",
        "description": "Reviews code for OWASP Top-10 vulnerabilities and provides a structured audit report.",
    },
    {
        "id": "scrum_master",
        "role": "Scrum Master",
        "icon": "🔄",
        "color": "#10b981",
        "description": "Produces the sprint retrospective with wins, blockers, improvements, and action items.",
    },
]

# Ordered list of agent ids — the canonical pipeline order.
AGENT_IDS: list[str] = [agent["id"] for agent in AGENTS]

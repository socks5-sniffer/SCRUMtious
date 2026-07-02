"""Domain models and metadata shared across the application.

Currently holds the canonical roster of Scrum agents used to render the UI.
Request/response shapes are validated inline in the route handlers to keep the
existing API contract and error messages stable.
"""

from typing import Any

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

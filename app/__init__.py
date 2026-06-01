"""SCRUMtious – AI Scrum Team Orchestration web application.

This package replaces the former single-file ``app.py`` monolith. Responsibilities
are split into focused modules:

- ``app.config``            – environment loading, validation, and settings
- ``app.models``            – domain constants / metadata (the agent roster)
- ``app.security``          – auth tokens, rate limiting, and HTTP security headers
- ``app.services``          – session persistence, CrewAI orchestration, PDF export
- ``app.api``               – FastAPI route handlers
- ``app.main``              – application factory (``create_app``) and the ASGI ``app``

Run with ``uvicorn app.main:app`` or ``python -m app``.
"""

__all__ = ["__version__"]

__version__ = "1.0.0"

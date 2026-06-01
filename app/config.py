"""Application configuration: environment loading, validation, and settings.

All runtime configuration is read from environment variables (optionally sourced
from a local ``.env`` file). Import this module for settings rather than calling
``os.getenv`` throughout the codebase.
"""

import logging
import os
import pathlib

from dotenv import load_dotenv

load_dotenv()

# --- Logging ---------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger("scrumtious.web")

# --- Required environment variables ----------------------------------------
# NOTE: the name ``_REQUIRED_ENV_VARS`` is asserted by the security CI workflow.
_REQUIRED_ENV_VARS = ["GEMINI_API_KEY"]
REQUIRED_ENV_VARS = _REQUIRED_ENV_VARS


def validate_required_env() -> None:
    """Fail fast at startup if any required environment variable is missing."""
    missing = [v for v in REQUIRED_ENV_VARS if not os.getenv(v)]
    if missing:
        raise OSError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Copy .env.example to .env and fill in your API keys."
        )


# --- Runtime settings ------------------------------------------------------
RUN_RATE_LIMIT_PER_MINUTE = int(os.getenv("RUN_RATE_LIMIT_PER_MINUTE", "5"))
SESSION_LIST_TOKEN = os.getenv("SESSION_LIST_TOKEN", "")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini/gemini-2.5-flash")

# Filesystem locations (relative to the working directory / repo root).
SESSIONS_DIR = pathlib.Path(os.getenv("SESSIONS_DIR", "sessions"))
TEMPLATES_DIR = "templates"
STATIC_DIR = "static"

# Server bind settings (used by ``python -m app``).
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

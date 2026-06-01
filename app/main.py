"""Application factory and ASGI entrypoint.

``create_app`` wires together configuration, middleware, static assets, the
session store, and the API router. The module-level ``app`` is the object served
by ``uvicorn app.main:app``.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import config
from app.api import router
from app.security.headers import add_security_headers
from app.services.session_store import store


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    config.validate_required_env()

    app = FastAPI(title="Scrumtious", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

    add_security_headers(app)

    # Re-hydrate completed sessions from disk before serving traffic.
    store.load_all()

    app.include_router(router)
    return app


app = create_app()

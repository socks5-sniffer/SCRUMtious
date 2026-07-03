"""Application factory and ASGI entrypoint.

``create_app`` wires together configuration, middleware, static assets, the
session store, and the API router. The module-level ``app`` is the object served
by ``uvicorn app.main:app``.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.api import router
from app.security.headers import add_security_headers
from app.services.session_store import store


async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Normalise Pydantic body-validation failures to the historical API contract:
    a 400 with ``{"error": <message>}`` instead of FastAPI's default 422 detail list.
    """
    message = "Invalid request body"
    errors = exc.errors()
    if errors:
        error_type = errors[0].get("type", "")
        if error_type in ("json_invalid", "missing"):
            message = "Request body must be valid JSON"
        elif error_type in ("model_attributes_type", "dict_type"):
            message = "Request body must be a JSON object"
        elif error_type == "string_type":
            field = errors[0].get("loc", ["body", "field"])[-1]
            message = f"Field '{field}' must be a string"
    return JSONResponse(status_code=400, content={"error": message})


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    config.validate_required_env()

    app = FastAPI(title="Scrumtious", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore[arg-type]

    add_security_headers(app)

    # Re-hydrate completed sessions from disk before serving traffic.
    store.load_all()

    app.include_router(router)
    return app


app = create_app()

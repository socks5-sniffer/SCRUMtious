"""FastAPI route handlers.

Thin HTTP layer: parses/validates requests, enforces auth and rate limits, and
delegates orchestration, persistence, and rendering to the service modules.
"""

import asyncio
import io
import json
import os
import re
import secrets
import threading
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app import config
from app.models import AGENTS, MAX_EDIT_LENGTH, MAX_IDEA_LENGTH, RunRequest
from app.security.auth import (
    is_local_request,
    resolve_session_token,
    session_token_valid,
)
from app.security.rate_limit import client_identifier, consume_run_token
from app.services import crew_runner, pdf_export
from app.services.session_store import store

router = APIRouter()
templates = Jinja2Templates(directory=config.TEMPLATES_DIR)


@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    """Serve favicon for browsers that request /favicon.ico directly."""
    return FileResponse(config.STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"agents": AGENTS},
    )


@router.post("/api/run")
async def start_run(request: Request, payload: RunRequest):
    idea = payload.idea
    tech_stack = payload.tech_stack
    security_framework = payload.security_framework or "OWASP Top-10"

    if not idea:
        return JSONResponse(status_code=400, content={"error": "Please provide an idea"})
    if len(idea) > MAX_IDEA_LENGTH:
        return JSONResponse(
            status_code=400,
            content={"error": f"Idea must be {MAX_IDEA_LENGTH} characters or fewer"},
        )

    # Each active sprint holds a worker thread and spends LLM quota.
    active_runs = sum(
        1 for s in store.sessions.values() if s.get("status") in ("running", "awaiting_approval")
    )
    if active_runs >= config.MAX_CONCURRENT_RUNS:
        return JSONResponse(
            status_code=429,
            content={"error": "Too many active sprints. Please wait for one to finish."},
        )

    # Only consume a rate-limit token for requests that will actually start a run.
    if not consume_run_token(client_identifier(request)):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded. Please wait before starting another sprint."},
        )

    session_id = str(uuid.uuid4())
    session_token = secrets.token_urlsafe(32)
    store.sessions[session_id] = {
        "status": "running",
        "events": [],
        "_task_idx": 0,
        "idea": idea,
        "tech_stack": tech_stack,
        "security_framework": security_framework,
        "created_at": datetime.now(UTC).isoformat(),
        "outputs": {},
        "verdict": "",
        "pending_approval": None,
        "access_token": session_token,
        "_hitl_event": threading.Event(),
        "_hitl_edit": None,
        "_edited_agents": [],
    }
    store.persist(session_id)

    thread = threading.Thread(
        target=crew_runner.run_crew_sync,
        args=(session_id, idea, tech_stack, security_framework),
        daemon=True,
    )
    thread.start()

    response = JSONResponse(content={"session_id": session_id, "session_token": session_token})
    response.set_cookie(
        key="scrumtious_session_token",
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=(request.url.scheme == "https" or os.getenv("COOKIE_SECURE", "0") == "1"),
        max_age=86400,
    )
    return response


@router.get("/api/stream/{session_id}")
async def stream_events(session_id: str, request: Request, token: str | None = None):
    session = store.sessions.get(session_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    auth_token = resolve_session_token(request, token)
    if not session_token_valid(session, auth_token):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})

    async def event_generator():
        last_idx = 0
        while True:
            session = store.sessions.get(session_id)
            if not session:
                break

            events = session["events"]
            while last_idx < len(events):
                event = events[last_idx]
                yield f"data: {json.dumps(event)}\n\n"
                last_idx += 1

            if session["status"] in ("complete", "error"):
                # Flush remaining events
                while last_idx < len(events):
                    event = events[last_idx]
                    yield f"data: {json.dumps(event)}\n\n"
                    last_idx += 1
                break

            # When paused for HITL the SSE stays open — client shows the approval UI
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/approve/{session_id}")
async def approve_step(session_id: str, request: Request, token: str | None = None):
    """Human-in-the-loop: approve the current agent output and continue the sprint.
    Optionally pass {"edit": "revised text"} to override the output before continuing.
    """
    session = store.sessions.get(session_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    auth_token = resolve_session_token(request, token)
    if not session_token_valid(session, auth_token):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    if session.get("status") != "awaiting_approval":
        return JSONResponse(status_code=409, content={"error": "Session is not awaiting approval"})

    body = {}
    try:
        body = await request.json()
    except Exception:
        # An empty or non-JSON body is valid here: approving without an edit
        # simply resumes the sprint, so fall back to the default empty dict.
        body = {}
    if not isinstance(body, dict):
        body = {}

    edit = body.get("edit")
    if edit is not None:
        edit_text = str(edit).strip()
        if len(edit_text) > MAX_EDIT_LENGTH:
            return JSONResponse(
                status_code=400,
                content={"error": f"Edit must be {MAX_EDIT_LENGTH} characters or fewer"},
            )
        session["_hitl_edit"] = edit_text

    # Unblock the background thread
    hitl_event_obj = session.get("_hitl_event")
    if isinstance(hitl_event_obj, threading.Event):
        hitl_event_obj.set()

    return JSONResponse(content={"ok": True})


@router.get("/api/sessions")
async def list_sessions(request: Request, token: str | None = None):
    """Return a list of all persisted sessions (most recent first)."""
    if not is_local_request(request):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    if not config.SESSION_LIST_TOKEN:
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    if not token or not _list_token_valid(token):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    results = []
    for sid, s in store.sessions.items():
        results.append({
            "session_id": sid,
            "idea": s.get("idea", ""),
            "status": s.get("status", ""),
            "created_at": s.get("created_at", ""),
            "verdict": s.get("verdict", ""),
            "pending_approval": s.get("pending_approval"),
        })
    results.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return JSONResponse(content=results)


@router.get("/api/sessions/{session_id}")
async def get_session(session_id: str, request: Request, token: str | None = None):
    """Return the persisted outputs for a completed session."""
    session = store.sessions.get(session_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    auth_token = resolve_session_token(request, token)
    if not session_token_valid(session, auth_token):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    return JSONResponse(content={
        "session_id": session_id,
        "idea": session.get("idea", ""),
        "tech_stack": session.get("tech_stack", ""),
        "security_framework": session.get("security_framework", ""),
        "status": session.get("status", ""),
        "created_at": session.get("created_at", ""),
        "verdict": session.get("verdict", ""),
        "outputs": session.get("outputs", {}),
        "pending_approval": session.get("pending_approval"),
    })


@router.get("/api/sessions/{session_id}/pdf")
async def export_session_pdf(session_id: str, request: Request, token: str | None = None):
    """Download a completed sprint session as a branded A4 PDF."""
    session = store.sessions.get(session_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    auth_token = resolve_session_token(request, token)
    if not session_token_valid(session, auth_token):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    if session.get("status") not in ("complete", "error"):
        return JSONResponse(
            status_code=409,
            content={"error": "Session must be complete before exporting PDF"},
        )

    try:
        pdf_bytes = pdf_export.build_sprint_pdf(session)
    except Exception:
        # session_id is a validated store key (a UUID we generated); strip any
        # CR/LF defensively so it can never forge log entries (CodeQL py/log-injection).
        safe_id = session_id.replace("\r", "").replace("\n", "")
        config.logger.exception("PDF export failed for session %s", safe_id)
        return JSONResponse(status_code=500, content={"error": "PDF generation failed"})

    idea_slug = re.sub(r"[^\w\s-]", "", session.get("idea", "sprint"))[:40]
    idea_slug = idea_slug.strip().replace(" ", "-").lower() or "sprint"
    filename = f"scrumtious-{idea_slug}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _list_token_valid(token: str) -> bool:
    """Constant-time comparison against the configured session-list token."""
    import hmac

    return hmac.compare_digest(config.SESSION_LIST_TOKEN, token)

"""
SCRUMtious – Web Frontend for AI Scrum Team Orchestration
=========================================================
FastAPI server that wraps the CrewAI workflow, streams agent progress
via Server-Sent Events, and serves a modern single-page UI.
"""

import asyncio
import json
import logging
import os
import pathlib
import re
import threading
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger("scrumtious.web")

# --- Validate required env vars at startup ---
_REQUIRED_ENV_VARS = ["GEMINI_API_KEY"]
_missing = [v for v in _REQUIRED_ENV_VARS if not os.getenv(v)]
if _missing:
    raise EnvironmentError(
        f"Missing required environment variable(s): {', '.join(_missing)}. "
        "Copy .env.example to .env and fill in your API keys."
    )

app = FastAPI(title="Scrumtious", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    """Serve favicon for browsers that request /favicon.ico directly."""
    return FileResponse("static/favicon.svg", media_type="image/svg+xml")

# --- JSON session persistence ---
_SESSIONS_DIR = pathlib.Path("sessions")
_SESSIONS_DIR.mkdir(exist_ok=True)

# In-memory session store (populated from disk on startup)
_sessions: dict[str, dict[str, Any]] = {}


def _session_path(session_id: str) -> pathlib.Path:
    return _SESSIONS_DIR / f"{session_id}.json"


def _persist_session(session_id: str) -> None:
    """Write the session's serialisable state to disk."""
    session = _sessions.get(session_id)
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
        _session_path(session_id).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        logger.exception("Failed to persist session %s", session_id)


def _load_all_sessions() -> None:
    """Re-hydrate completed sessions from disk into _sessions on startup."""
    for p in _SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            sid = data.get("session_id", p.stem)
            _sessions[sid] = {
                **data,
                "events": [],
                "_task_idx": 0,
                "_hitl_event": None,  # not resumable after restart
            }
        except Exception:
            logger.warning("Could not load session file %s", p)


_load_all_sessions()

AGENTS = [
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
        "description": "Implements secure Python code following OWASP practices with full input validation.",
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


def _extract_verdict(audit_output: str) -> str:
    structured = re.search(
        r"\bverdict\s*[:\-]\s*(approved|blocked)\b",
        audit_output,
        re.IGNORECASE,
    )
    if structured:
        return structured.group(1).upper()
    matches = list(re.finditer(r"\b(APPROVED|BLOCKED)\b", audit_output.upper()))
    if matches:
        return matches[-1].group(1)
    return "UNKNOWN"


def _build_error_payload(exc: Exception) -> dict[str, str]:
    """Build a user-facing error payload while preserving raw diagnostics."""
    raw_message = str(exc)
    lower = raw_message.lower()

    message = raw_message
    hint = "Check server logs for traceback details."

    if (
        "api key expired" in lower
        or "api_key_invalid" in lower
        or "invalid api key" in lower
    ):
        message = "Gemini authentication failed: API key expired or invalid."
        hint = (
            "Set a fresh GEMINI_API_KEY in .env (Google AI Studio), "
            "then restart the server."
        )
    elif "no longer available" in lower or "not supported for generatecontent" in lower:
        message = "Gemini model is deprecated or unavailable for this project."
        hint = "Set GEMINI_MODEL to a current model (for example: gemini/gemini-2.5-flash)."
    elif "quota" in lower or "rate" in lower:
        message = "Gemini request was rejected due to quota/rate limits."
        hint = "Check project quota limits and retry later."

    return {
        "message": message,
        "error_type": type(exc).__name__,
        "hint": hint,
        "raw_error": raw_message,
        "traceback": traceback.format_exc(),
    }


def _run_crew_sync(session_id: str, idea: str, tech_stack: str = "", security_framework: str = "OWASP Top-10") -> None:
    """Run the CrewAI crew in a background thread, pushing events to the session."""
    from crewai import Agent, Crew, Task, LLM

    session = _sessions[session_id]
    current_datetime_utc = datetime.now(timezone.utc)
    current_datetime_label = current_datetime_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    current_date_context = (
        f"Current UTC date and time: {current_datetime_label}. "
        "Use this current date/time for any headers, metadata, timestamps, sprint periods, "
        "retrospective dates, or action-item due dates that you include. "
        "Do not use placeholder/example dates or prior-year dates such as 2023 unless the user explicitly asks for them."
    )

    gemini_model = os.getenv("GEMINI_MODEL", "gemini/gemini-2.5-flash")
    gemini_llm = LLM(
        model=gemini_model,
        api_key=os.getenv("GEMINI_API_KEY"),
    )

    stack_context = f" The target technology stack is: {tech_stack}." if tech_stack else ""
    security_context = security_framework or "OWASP Top-10"

    def push_event(event_type: str, data: dict):
        session["events"].append({"type": event_type, **data})

    try:
        # --- Agents ---
        business_analyst = Agent(
            role="Business Analyst",
            goal=(
                "Translate raw feature ideas into structured, unambiguous, "
                "dev-ready requirements with personas, constraints, acceptance criteria, "
                "and edge cases."
            ),
            backstory=(
                "You are a meticulous Business Analyst with deep experience bridging "
                "the gap between stakeholders and engineering teams across a wide range "
                "of software and hardware projects."
            ),
            verbose=True,
            allow_delegation=False,
            llm=gemini_llm,
        )

        product_owner = Agent(
            role="Product Owner",
            goal=(
                "Manage the product backlog and define clear, actionable technical "
                "user stories that prioritise security best practices and "
                "deliver genuine value to end users."
            ),
            backstory=(
                "You are a seasoned Product Owner with broad experience across web, "
                "mobile, embedded systems, and API products."
            ),
            verbose=True,
            allow_delegation=False,
            llm=gemini_llm,
        )

        lead_developer = Agent(
            role="Lead Developer",
            goal=(
                "Implement production-quality code following strict secure-coding patterns: "
                "validate all inputs, avoid dangerous built-ins, "
                "and always include proper error handling."
            ),
            backstory=(
                "You are a full-stack developer with experience across web, API, "
                "and embedded systems projects. You write clean, well-documented, "
                "production-quality code."
            ),
            verbose=True,
            allow_delegation=False,
            llm=gemini_llm,
        )

        security_auditor = Agent(
            role="Security Auditor",
            goal=(
                "Review all code for OWASP Top-10 vulnerabilities and Principle of "
                "Least Privilege violations. Block any artefact with eval(), missing "
                "error handling, or exposed sensitive data."
            ),
            backstory=(
                "You are a certified application-security engineer with deep knowledge "
                "of OWASP, CWE, and threat modelling across web, API, and systems software."
            ),
            verbose=True,
            allow_delegation=False,
            llm=gemini_llm,
        )

        scrum_master = Agent(
            role="Scrum Master",
            goal=(
                "After each sprint, produce a structured retrospective that captures "
                "what went well, what was blocked, process improvements, and "
                "prioritised follow-up actions."
            ),
            backstory=(
                "You are a Certified Scrum Master who has facilitated hundreds of "
                "sprints across diverse software teams and technology stacks."
            ),
            verbose=True,
            allow_delegation=False,
            llm=gemini_llm,
        )

        # --- Tasks ---
        push_event("agent_start", {"agent": "business_analyst"})

        task_refine = Task(
            description=(
                f"A new feature idea has arrived: '{idea}'.{stack_context} Transform it into a "
                "structured requirements document with user stories, acceptance "
                "criteria, edge cases, and any relevant safety or integration notes. "
                f"{current_date_context}"
            ),
            expected_output="A structured requirements document with user stories and acceptance criteria.",
            agent=business_analyst,
        )

        task_user_story = Task(
            description=(
                "Review the Business Analyst's requirements and create a sprint-ready "
                "user story with acceptance criteria, technical details, security notes, "
                "and learning objectives. "
                f"{current_date_context}"
            ),
            expected_output="A complete sprint-ready user story.",
            agent=product_owner,
            context=[task_refine],
        )

        task_implement = Task(
            description=(
                f"Using the user story, write the implementation.{stack_context} "
                "Sanitise inputs, use specific exception types, never use eval(), and "
                f"follow {security_context} Secure Coding Practices. {current_date_context}"
            ),
            expected_output="Complete, commented source code with security measures applied.",
            agent=lead_developer,
            context=[task_user_story],
        )

        task_audit = Task(
            description=(
                f"Perform a security audit of the implementation using the {security_context} framework. "
                "Verify least privilege, reject eval()/exec()/shell=True/bare excepts. "
                f"Produce a structured audit report with APPROVED or BLOCKED verdict. {current_date_context}"
            ),
            expected_output="A structured security audit report with a final verdict.",
            agent=security_auditor,
            context=[task_implement],
        )

        task_retro = Task(
            description=(
                "Review all outputs and produce a sprint retrospective with: what went "
                "well, blockers, at least 3 process improvements, prioritised action "
                f"items with owners, and sprint-goal verdict. {current_date_context}"
            ),
            expected_output="A structured sprint retrospective report.",
            agent=scrum_master,
            context=[task_refine, task_user_story, task_implement, task_audit],
        )

        agents_list = [business_analyst, product_owner, lead_developer, security_auditor, scrum_master]
        tasks_list = [task_refine, task_user_story, task_implement, task_audit, task_retro]

        agent_task_map = {
            id(task_refine): "business_analyst",
            id(task_user_story): "product_owner",
            id(task_implement): "lead_developer",
            id(task_audit): "security_auditor",
            id(task_retro): "scrum_master",
        }

        def _safe_step_callback(*_args, **_kwargs):
            # CrewAI callback signatures vary across versions; ignore payload safely.
            return None

        def _safe_task_callback(*args, **kwargs):
            """Version-tolerant task callback wrapper.

            CrewAI has changed callback invocation signatures over releases.
            This wrapper extracts the first positional argument when present and
            prevents callback errors from aborting the whole crew execution.
            """
            task_output = args[0] if args else kwargs.get("task_output")
            try:
                _on_task_complete(session_id, task_output, agent_task_map, tasks_list)
            except Exception:
                logger.exception("Task callback failed for session %s", session_id)

        crew = Crew(
            agents=agents_list,
            tasks=tasks_list,
            verbose=True,
            step_callback=_safe_step_callback,
            task_callback=_safe_task_callback,
        )

        result = crew.kickoff()

        verdict = _extract_verdict(str(result))
        session["verdict"] = verdict
        push_event("complete", {
            "verdict": verdict,
            "result": str(result),
        })
        session["status"] = "complete"
        _persist_session(session_id)

    except Exception as e:
        logger.exception("Crew execution failed")
        push_event("error", _build_error_payload(e))
        session["status"] = "error"
        _persist_session(session_id)


def _on_task_complete(session_id: str, task_output, agent_task_map, tasks_list):
    """Called when a CrewAI task finishes. Pauses for human approval before continuing."""
    session = _sessions.get(session_id)
    if not session:
        return

    agent_ids = ["business_analyst", "product_owner", "lead_developer", "security_auditor", "scrum_master"]
    completed_idx = session.get("_task_idx", 0)

    if completed_idx < len(agent_ids):
        agent_id = agent_ids[completed_idx]
        output_text = getattr(task_output, "raw", None) or str(task_output) if task_output else ""

        # Store output in persistent dict
        session["outputs"][agent_id] = output_text

        # Emit agent_complete — also includes approval prompt for all but the last agent
        is_last = completed_idx == len(agent_ids) - 1
        session["events"].append({
            "type": "agent_complete",
            "agent": agent_id,
            "output": output_text,
            "needs_approval": not is_last,
        })

        # Persist after each agent completes
        _persist_session(session_id)

        if not is_last:
            # Pause the crew thread until the user approves (or edits)
            session["status"] = "awaiting_approval"
            session["pending_approval"] = agent_id
            _persist_session(session_id)

            hitl_event: threading.Event = session["_hitl_event"]
            hitl_event.clear()
            hitl_event.wait()  # blocks the background thread here

            # Apply any user edit
            edit = session.get("_hitl_edit")
            if edit is not None:
                session["outputs"][agent_id] = edit
                session["events"].append({
                    "type": "agent_edited",
                    "agent": agent_id,
                    "output": edit,
                })
                session["_hitl_edit"] = None

            session["status"] = "running"
            session["pending_approval"] = None

            # Signal the next agent is starting
            next_idx = completed_idx + 1
            session["events"].append({
                "type": "agent_start",
                "agent": agent_ids[next_idx],
            })

    session["_task_idx"] = completed_idx + 1


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"agents": AGENTS},
    )


@app.post("/api/run")
async def start_run(request: Request):
    body = await request.json()
    idea = body.get("idea", "").strip()
    tech_stack = body.get("tech_stack", "").strip()
    security_framework = body.get("security_framework", "OWASP Top-10").strip()

    if not idea:
        return JSONResponse(status_code=400, content={"error": "Please provide an idea"})
    if len(idea) > 2000:
        return JSONResponse(status_code=400, content={"error": "Idea must be 2000 characters or fewer"})

    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "status": "running",
        "events": [],
        "_task_idx": 0,
        "idea": idea,
        "tech_stack": tech_stack,
        "security_framework": security_framework,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "outputs": {},
        "verdict": "",
        "pending_approval": None,
        "_hitl_event": threading.Event(),
        "_hitl_edit": None,
    }
    _persist_session(session_id)

    thread = threading.Thread(
        target=_run_crew_sync,
        args=(session_id, idea, tech_stack, security_framework),
        daemon=True,
    )
    thread.start()

    return JSONResponse(content={"session_id": session_id})


@app.get("/api/stream/{session_id}")
async def stream_events(session_id: str):
    if session_id not in _sessions:
        return {"error": "Session not found"}, 404

    async def event_generator():
        last_idx = 0
        while True:
            session = _sessions.get(session_id)
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


@app.post("/api/approve/{session_id}")
async def approve_step(session_id: str, request: Request):
    """Human-in-the-loop: approve the current agent output and continue the sprint.
    Optionally pass {"edit": "revised text"} to override the output before continuing.
    """
    session = _sessions.get(session_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    if session.get("status") != "awaiting_approval":
        return JSONResponse(status_code=409, content={"error": "Session is not awaiting approval"})

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    edit = body.get("edit")
    if edit is not None:
        session["_hitl_edit"] = str(edit).strip()

    # Unblock the background thread
    hitl_event: threading.Event = session.get("_hitl_event")
    if hitl_event:
        hitl_event.set()

    return JSONResponse(content={"ok": True})


@app.get("/api/sessions")
async def list_sessions():
    """Return a list of all persisted sessions (most recent first)."""
    results = []
    for sid, s in _sessions.items():
        results.append({
            "session_id": sid,
            "idea": s.get("idea", ""),
            "status": s.get("status", ""),
            "created_at": s.get("created_at", ""),
            "verdict": s.get("verdict", ""),
            "pending_approval": s.get("pending_approval"),
        })
    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return JSONResponse(content=results)


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Return the persisted outputs for a completed session."""
    session = _sessions.get(session_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
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


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host=host, port=port, reload=True)

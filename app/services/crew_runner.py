"""CrewAI orchestration with a human-in-the-loop (HITL) gate between agents.

``run_crew_sync`` executes the five-agent sprint pipeline in a background thread,
appending events to the session's in-memory queue (consumed by the SSE stream)
and pausing after each agent for human approval. CrewAI itself is imported lazily
so the rest of the app (and the test suite) can run without the heavy dependency.
"""

import os
import re
import threading
from datetime import UTC, datetime

from app.config import GEMINI_MODEL, logger
from app.models import AGENT_IDS
from app.services.session_store import store


def extract_verdict(audit_output: str) -> str:
    """Pull an APPROVED/BLOCKED verdict out of the auditor's free-text report."""
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


def build_error_payload(exc: Exception) -> dict[str, str]:
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
        "hint": hint,
    }


def run_crew_sync(
    session_id: str,
    idea: str,
    tech_stack: str = "",
    security_framework: str = "OWASP Top-10",
) -> None:
    """Run the CrewAI crew in a background thread, pushing events to the session."""
    from crewai import LLM, Agent, Crew, Task

    session = store.sessions[session_id]
    current_datetime_utc = datetime.now(UTC)
    current_datetime_label = current_datetime_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    current_date_context = (
        f"Current UTC date and time: {current_datetime_label}. "
        "Use this current date/time for any headers, metadata, timestamps, sprint periods, "
        "retrospective dates, or action-item due dates that you include. "
        "Do not use placeholder/example dates or prior-year dates such as 2023 unless the user explicitly asks for them."
    )

    gemini_model = os.getenv("GEMINI_MODEL", GEMINI_MODEL)
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

        audit_text = session.get("outputs", {}).get("security_auditor") or str(result)
        verdict = extract_verdict(audit_text)
        session["verdict"] = verdict
        push_event("complete", {
            "verdict": verdict,
            "result": str(result),
        })
        session["status"] = "complete"
        store.persist(session_id)

    except Exception as e:
        logger.exception("Crew execution failed")
        push_event("error", build_error_payload(e))
        session["status"] = "error"
        store.persist(session_id)


def _on_task_complete(session_id: str, task_output, agent_task_map, tasks_list):
    """Called when a CrewAI task finishes. Pauses for human approval before continuing."""
    session = store.sessions.get(session_id)
    if not session:
        return

    agent_ids = AGENT_IDS
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
        store.persist(session_id)

        if not is_last:
            # Pause the crew thread until the user approves (or edits)
            session["status"] = "awaiting_approval"
            session["pending_approval"] = agent_id
            store.persist(session_id)

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

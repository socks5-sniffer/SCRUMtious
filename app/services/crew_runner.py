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
from typing import Any

from app.config import GEMINI_MODEL, logger
from app.models import AGENT_IDS
from app.services.agent_prompts import AGENT_PROMPTS
from app.services.session_store import store


def extract_verdict(audit_output: str) -> str:
    """Pull an APPROVED/BLOCKED verdict out of the auditor's report.

    The audit prompt requires a terminal ``VERDICT: APPROVED|BLOCKED`` line, so
    the last structured match wins; keyword scanning remains as a fallback for
    reports that ignore the format.
    """
    structured = list(
        re.finditer(
            r"\bverdict\s*[:\-]\s*(approved|blocked)\b",
            audit_output,
            re.IGNORECASE,
        )
    )
    if structured:
        return structured[-1].group(1).upper()
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

    gemini_llm = LLM(
        model=GEMINI_MODEL,
        api_key=os.getenv("GEMINI_API_KEY"),
    )

    security_context = security_framework or "OWASP Top-10"
    prompt_values = {
        "idea": idea,
        "stack_context": f" The target technology stack is: {tech_stack}." if tech_stack else "",
        "stack_clause": f" in {tech_stack}" if tech_stack else "",
        "security_framework": security_context,
        "date_context": current_date_context,
    }

    def push_event(event_type: str, data: dict):
        session["events"].append({"type": event_type, **data})

    try:
        # Build agents and tasks from the declarative specs, preserving
        # pipeline order (AGENT_IDS) and the context wiring between tasks.
        agents: dict[str, Any] = {}
        tasks: dict[str, Any] = {}
        for agent_id in AGENT_IDS:
            spec = AGENT_PROMPTS[agent_id]
            agents[agent_id] = Agent(
                role=spec["role"],
                goal=spec["goal"].format(**prompt_values),
                backstory=spec["backstory"].format(**prompt_values),
                verbose=True,
                allow_delegation=False,
                llm=gemini_llm,
            )
        for agent_id in AGENT_IDS:
            spec = AGENT_PROMPTS[agent_id]
            task_kwargs: dict[str, Any] = {}
            if spec["context"]:
                task_kwargs["context"] = [tasks[dep] for dep in spec["context"]]
            tasks[agent_id] = Task(
                description=spec["description"].format(**prompt_values),
                expected_output=spec["expected_output"],
                agent=agents[agent_id],
                **task_kwargs,
            )

        agents_list = list(agents.values())
        tasks_list = list(tasks.values())
        agent_task_map = {id(task): agent_id for agent_id, task in tasks.items()}

        push_event("agent_start", {"agent": AGENT_IDS[0]})

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
                # Downstream tasks read their context from the CrewAI task
                # output, not from session["outputs"], so the edit must be
                # written back there too or the next agent sees the original.
                _apply_edit_to_task_output(tasks_list[completed_idx], task_output, edit)
                session.setdefault("_edited_agents", []).append(agent_id)
                session["events"].append({
                    "type": "agent_edited",
                    "agent": agent_id,
                    "output": edit,
                })
                session["_hitl_edit"] = None

            session["status"] = "running"
            session["pending_approval"] = None

            # Persist the resumed state (including any applied edit) so a restart
            # after approval doesn't leave the on-disk copy stuck awaiting approval.
            store.persist(session_id)

            # Signal the next agent is starting
            next_idx = completed_idx + 1
            next_agent = agent_ids[next_idx]
            if next_agent == "scrum_master":
                _inject_pipeline_facts(session, tasks_list[next_idx])
            session["events"].append({
                "type": "agent_start",
                "agent": next_agent,
            })

    session["_task_idx"] = completed_idx + 1


def _apply_edit_to_task_output(task, task_output, edit: str) -> None:
    """Write a human edit into the CrewAI task output.

    Downstream tasks build their context from ``task.output.raw``; both the
    callback argument and the task's own output attribute are updated in case
    the installed CrewAI version passes a copy rather than the same object.
    """
    targets: list[Any] = []
    for candidate in (task_output, getattr(task, "output", None)):
        if candidate is not None and not any(candidate is t for t in targets):
            targets.append(candidate)
    for target in targets:
        try:
            target.raw = edit
        except Exception:
            logger.warning(
                "Could not apply HITL edit to task output of type %s",
                type(target).__name__,
            )


def _inject_pipeline_facts(session: dict, retro_task) -> None:
    """Give the Scrum Master real process facts before the retrospective runs.

    The retro otherwise only sees the four documents; whether a human had to
    override an agent's output is exactly the kind of process signal a
    retrospective should discuss.
    """
    edited = session.get("_edited_agents") or []
    if edited:
        facts = (
            " Pipeline facts for this sprint: a human reviewer edited the output of "
            f"the following team member(s) before approving: {', '.join(edited)}. "
            "Discuss in the retrospective why these outputs needed human correction "
            "and how the process could avoid it next sprint."
        )
    else:
        facts = (
            " Pipeline facts for this sprint: every hand-off was approved by the "
            "human reviewer without edits."
        )
    try:
        retro_task.description = retro_task.description + facts
    except Exception:
        logger.warning("Could not append pipeline facts to the retrospective task")

"""Exercise the installed CrewAI API without provider calls or network access."""

import socket
import threading

import pytest

from app.models import AGENT_IDS
from app.services import crew_runner
from app.services.session_store import store


def test_installed_crewai_pipeline_callbacks(tmp_path, monkeypatch):
    def refuse_network(*args, **kwargs):
        raise AssertionError("CrewAI compatibility test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", refuse_network)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse_network)
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.setenv("CREWAI_TRACING_ENABLED", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "offline-compatibility-test-key")
    crewai = pytest.importorskip("crewai")
    from crewai.tasks.task_output import TaskOutput

    class ApprovedEvent(threading.Event):
        def wait(self, timeout=None):
            return True

    monkeypatch.setattr(store, "dir", tmp_path)
    monkeypatch.setattr(store, "sessions", {})
    session = {
        "status": "running",
        "events": [],
        "outputs": {},
        "idea": "offline compatibility check",
        "_task_idx": 0,
        "_hitl_event": ApprovedEvent(),
        "_hitl_edit": None,
        "_edited_agents": [],
    }
    store.sessions["compat"] = session

    def kickoff_without_provider(self):
        assert self.memory is False
        assert len(self.tasks) == len(AGENT_IDS)
        for task in self.tasks:
            output = TaskOutput(
                description=task.description,
                agent=task.agent.role,
                raw="VERDICT: APPROVED",
            )
            task.output = output
            self.task_callback(output)
        return output

    monkeypatch.setattr(crewai.Crew, "kickoff", kickoff_without_provider)
    crew_runner.run_crew_sync("compat", session["idea"])

    assert session["status"] == "complete"
    assert list(session["outputs"]) == AGENT_IDS
    assert session["verdict"] == "APPROVED"
    assert session["events"][-1]["type"] == "complete"
    assert not crew_runner._stream_targets

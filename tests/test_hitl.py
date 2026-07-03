"""Tests for the HITL approval flow inside the crew runner.

Uses fake task objects and a non-blocking event so ``_on_task_complete`` can be
exercised without CrewAI or a live crew thread.
"""

import threading

import pytest

from app.services import crew_runner
from app.services.session_store import store


class _NoWaitEvent(threading.Event):
    """HITL gate that never blocks — approval is treated as already granted."""

    def wait(self, timeout=None):
        return True


class _FakeTaskOutput:
    def __init__(self, raw):
        self.raw = raw


class _FakeTask:
    def __init__(self, raw=None, description="desc"):
        self.output = _FakeTaskOutput(raw) if raw is not None else None
        self.description = description


def _make_session(tmp_path, monkeypatch, **overrides):
    monkeypatch.setattr(store, "dir", tmp_path / "sessions")
    store.dir.mkdir(parents=True, exist_ok=True)
    store.sessions.clear()
    session = {
        "status": "running",
        "events": [],
        "_task_idx": 0,
        "idea": "demo",
        "outputs": {},
        "verdict": "",
        "pending_approval": None,
        "access_token": "tok",
        "created_at": "2026-07-02T00:00:00+00:00",
        "_hitl_event": _NoWaitEvent(),
        "_hitl_edit": None,
        "_edited_agents": [],
    }
    session.update(overrides)
    store.sessions["sid"] = session
    return session


def test_hitl_edit_reaches_downstream_task_context(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch, _hitl_edit="EDITED requirements")
    task_output = _FakeTaskOutput("original")
    tasks_list = [_FakeTask("original")] + [_FakeTask() for _ in range(4)]

    crew_runner._on_task_complete("sid", task_output, tasks_list)

    # The edit must land everywhere the next agent could read from: the session
    # outputs (UI/PDF) and the CrewAI task output (downstream task context).
    assert session["outputs"]["business_analyst"] == "EDITED requirements"
    assert task_output.raw == "EDITED requirements"
    assert tasks_list[0].output.raw == "EDITED requirements"
    assert session["_edited_agents"] == ["business_analyst"]
    assert session["_hitl_edit"] is None
    assert session["_task_idx"] == 1

    event_types = [e["type"] for e in session["events"]]
    assert event_types == ["agent_complete", "agent_edited", "agent_start"]


def test_approval_without_edit_leaves_output_untouched(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    task_output = _FakeTaskOutput("original")
    tasks_list = [_FakeTask("original")] + [_FakeTask() for _ in range(4)]

    crew_runner._on_task_complete("sid", task_output, tasks_list)

    assert session["outputs"]["business_analyst"] == "original"
    assert task_output.raw == "original"
    assert session["_edited_agents"] == []


def test_retro_task_receives_pipeline_facts_about_edits(tmp_path, monkeypatch):
    _make_session(tmp_path, monkeypatch, _task_idx=3, _edited_agents=["product_owner"])
    tasks_list = [_FakeTask("out") for _ in range(5)]

    crew_runner._on_task_complete("sid", _FakeTaskOutput("audit report"), tasks_list)

    retro_description = tasks_list[4].description
    assert "product_owner" in retro_description
    assert "edited" in retro_description
    # Earlier tasks are untouched.
    assert tasks_list[2].description == "desc"


def test_retro_task_receives_no_edit_facts(tmp_path, monkeypatch):
    _make_session(tmp_path, monkeypatch, _task_idx=3)
    tasks_list = [_FakeTask("out") for _ in range(5)]

    crew_runner._on_task_complete("sid", _FakeTaskOutput("audit report"), tasks_list)

    assert "without edits" in tasks_list[4].description


def test_hitl_timeout_aborts_sprint(tmp_path, monkeypatch):
    # A real Event that is never set: the wait must give up and abort the crew.
    monkeypatch.setattr(crew_runner, "HITL_TIMEOUT_SECONDS", 0)
    session = _make_session(tmp_path, monkeypatch, _hitl_event=threading.Event())
    tasks_list = [_FakeTask("out") for _ in range(5)]

    with pytest.raises(crew_runner.HitlTimeoutError):
        crew_runner._on_task_complete("sid", _FakeTaskOutput("original"), tasks_list)

    assert session["status"] == "error"
    assert session["_hitl_timed_out"] is True
    assert session["pending_approval"] is None
    assert session["events"][-1]["type"] == "error"


def test_hitl_gate_rearmed_before_awaiting_approval(tmp_path, monkeypatch):
    # /api/approve only sets the event once status == awaiting_approval, so
    # clear() must run BEFORE the status flips — otherwise a fast approval
    # could be wiped and the sprint would block until timeout.
    observed = {}

    class _RecordingEvent(threading.Event):
        def clear(self):
            observed["status_at_clear"] = store.sessions["sid"]["status"]
            super().clear()

        def wait(self, timeout=None):
            return True

    _make_session(tmp_path, monkeypatch, _hitl_event=_RecordingEvent())
    tasks_list = [_FakeTask("out") for _ in range(5)]

    crew_runner._on_task_complete("sid", _FakeTaskOutput("original"), tasks_list)

    assert observed["status_at_clear"] == "running"


def test_missing_hitl_event_marks_session_errored(tmp_path, monkeypatch):
    # A session that somehow lacks a live approval gate must fail visibly,
    # not sit in awaiting_approval forever.
    session = _make_session(tmp_path, monkeypatch, _hitl_event=None)
    tasks_list = [_FakeTask("out") for _ in range(5)]

    with pytest.raises(crew_runner.HitlTimeoutError):
        crew_runner._on_task_complete("sid", _FakeTaskOutput("original"), tasks_list)

    assert session["status"] == "error"
    assert session["pending_approval"] is None
    assert session["events"][-1]["type"] == "error"


def test_spurious_callback_beyond_pipeline_is_ignored(tmp_path, monkeypatch):
    # An unexpected extra callback after the last task must not advance the
    # cursor, emit events, or record outputs.
    session = _make_session(tmp_path, monkeypatch, _task_idx=5)
    tasks_list = [_FakeTask("out") for _ in range(5)]

    crew_runner._on_task_complete("sid", _FakeTaskOutput("extra"), tasks_list)

    assert session["_task_idx"] == 5
    assert session["events"] == []
    assert session["outputs"] == {}


def test_last_agent_completion_needs_no_approval(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch, _task_idx=4)
    tasks_list = [_FakeTask("out") for _ in range(5)]

    crew_runner._on_task_complete("sid", _FakeTaskOutput("retro"), tasks_list)

    assert session["outputs"]["scrum_master"] == "retro"
    assert session["status"] == "running"  # completion event is emitted by run_crew_sync
    last_event = session["events"][-1]
    assert last_event["type"] == "agent_complete"
    assert last_event["needs_approval"] is False

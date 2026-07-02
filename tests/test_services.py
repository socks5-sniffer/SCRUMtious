"""Unit tests for service- and security-layer helpers."""

import pytest

from app.models import AGENT_IDS
from app.services import crew_runner
from app.services.agent_prompts import AGENT_PROMPTS
from app.services.pdf_export import build_sprint_pdf
from app.services.session_store import SessionStore


def test_extract_verdict_structured():
    assert crew_runner.extract_verdict("Final Verdict: APPROVED") == "APPROVED"
    assert crew_runner.extract_verdict("verdict - blocked") == "BLOCKED"


def test_extract_verdict_prefers_last_structured_line():
    # The prompt mandates a terminal VERDICT line; an earlier mention must lose.
    report = "Draft verdict: BLOCKED pending fixes.\n...fixes applied...\nVERDICT: APPROVED"
    assert crew_runner.extract_verdict(report) == "APPROVED"


def test_extract_verdict_falls_back_to_last_keyword():
    assert crew_runner.extract_verdict("was BLOCKED, now APPROVED") == "APPROVED"


def test_extract_verdict_unknown():
    assert crew_runner.extract_verdict("no decision here") == "UNKNOWN"


def test_agent_prompts_match_pipeline():
    # The prompt specs are the single source of truth for the crew; they must
    # stay in lockstep with the canonical agent roster.
    assert list(AGENT_PROMPTS) == AGENT_IDS
    for spec in AGENT_PROMPTS.values():
        for dep in spec["context"]:
            assert dep in AGENT_PROMPTS


def test_agent_prompt_templates_format_cleanly():
    values = {
        "idea": "an idea with {braces} and 'quotes'",  # braces in user input are values, not templates
        "stack_context": " The target technology stack is: Python/FastAPI.",
        "stack_clause": " in Python/FastAPI",
        "security_framework": "OWASP Top-10",
        "date_context": "Current UTC date and time: 2026-07-02.",
    }
    for spec in AGENT_PROMPTS.values():
        for key in ("goal", "backstory", "description"):
            rendered = spec[key].format(**values)
            assert rendered
        assert spec["expected_output"]


def test_auditor_prompt_demands_machine_readable_verdict():
    description = AGENT_PROMPTS["security_auditor"]["description"]
    assert "VERDICT: APPROVED" in description
    assert "VERDICT: BLOCKED" in description


def test_build_error_payload_classifies_auth_failure():
    payload = crew_runner.build_error_payload(Exception("API key expired"))
    assert payload["message"].startswith("Gemini authentication")
    assert "GEMINI_API_KEY" in payload["hint"]


def test_build_error_payload_classifies_quota():
    payload = crew_runner.build_error_payload(Exception("quota exceeded"))
    assert "quota" in payload["message"].lower()


def test_session_store_persist_and_load_roundtrip(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    store.sessions["abc"] = {
        "idea": "demo",
        "status": "complete",
        "outputs": {"business_analyst": "hi"},
        "verdict": "APPROVED",
        "created_at": "2026-05-31T00:00:00+00:00",
        "access_token": "tok-123",
        "events": [{"type": "x"}],            # transient, not persisted
        "_hitl_event": object(),              # transient, not persisted
    }
    store.persist("abc")

    reloaded = SessionStore(tmp_path / "sessions")
    reloaded.load_all()
    assert "abc" in reloaded.sessions
    s = reloaded.sessions["abc"]
    assert s["idea"] == "demo"
    assert s["verdict"] == "APPROVED"
    assert s["outputs"] == {"business_analyst": "hi"}
    # The access token must survive a restart so the owner stays authorised.
    assert s["access_token"] == "tok-123"
    # Transient fields are reset, not restored from disk.
    assert s["events"] == []
    assert s["_hitl_event"] is None


def test_load_all_marks_interrupted_sessions_as_error(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    store.sessions["mid"] = {
        "idea": "x",
        "status": "awaiting_approval",
        "created_at": "2026-05-31T00:00:00+00:00",
        "_hitl_event": object(),
    }
    store.persist("mid")

    reloaded = SessionStore(tmp_path / "sessions")
    reloaded.load_all()
    # A run that was mid-flight cannot resume after restart -> errored, not stuck.
    assert reloaded.sessions["mid"]["status"] == "error"


def test_session_store_creates_nested_dir(tmp_path):
    # Should not raise even when the parent directories do not exist yet.
    store = SessionStore(tmp_path / "a" / "b" / "sessions")
    assert store.dir.is_dir()


def test_build_sprint_pdf_escapes_metadata(tmp_path):
    # HTML-special characters in metadata must not break PDF generation.
    pdf = build_sprint_pdf({
        "idea": "a < b & c > <script>x</script>",
        "verdict": "APPROVED",
        "created_at": "2026-05-31T00:00:00+00:00",
        "outputs": {"business_analyst": "# ok"},
    })
    assert pdf[:4] == b"%PDF"


def test_build_sprint_pdf_blocks_external_resources():
    # An external/file image smuggled via Markdown must be refused (fail closed).
    with pytest.raises(ValueError):
        build_sprint_pdf({
            "idea": "x",
            "verdict": "BLOCKED",
            "created_at": "2026-05-31T00:00:00+00:00",
            "outputs": {"lead_developer": "![p](http://169.254.169.254/latest) ![f](file:///etc/passwd)"},
        })


def test_build_sprint_pdf_returns_pdf_bytes():
    session = {
        "idea": "demo idea",
        "verdict": "APPROVED",
        "created_at": "2026-05-31T00:00:00+00:00",
        "outputs": {"business_analyst": "# Title\n- bullet"},
    }
    pdf = build_sprint_pdf(session)
    assert pdf[:4] == b"%PDF"

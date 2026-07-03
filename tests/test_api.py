"""HTTP-layer tests for the FastAPI routes."""


def _start_run(client, idea="build a todo app"):
    resp = client.post("/api/run", json={"idea": idea})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["session_id"], body["session_token"]


def test_index_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "SCRUMtious" in resp.text


def test_run_rejects_malformed_json(client):
    resp = client.post("/api/run", content="not json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 400
    assert "JSON" in resp.json()["error"]


def test_run_requires_idea(client):
    resp = client.post("/api/run", json={"idea": "   "})
    assert resp.status_code == 400
    assert resp.json()["error"] == "Please provide an idea"


def test_run_rejects_oversized_idea(client):
    resp = client.post("/api/run", json={"idea": "x" * 2001})
    assert resp.status_code == 400
    assert "2000 characters" in resp.json()["error"]


def test_run_issues_session_and_cookie(client):
    resp = client.post("/api/run", json={"idea": "build a todo app"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] and body["session_token"]
    assert "scrumtious_session_token" in resp.cookies


def test_session_access_requires_valid_token(client):
    session_id, token = _start_run(client)
    assert client.get(f"/api/sessions/{session_id}?token=wrong").status_code == 403
    assert client.get(f"/api/sessions/{session_id}?token={token}").status_code == 200


def test_unknown_session_is_404(client):
    assert client.get("/api/sessions/nope?token=x").status_code == 404


def test_pdf_export_blocked_until_complete(client):
    session_id, token = _start_run(client)
    assert client.get(f"/api/sessions/{session_id}/pdf?token={token}").status_code == 409


def test_approve_rejected_when_not_awaiting(client):
    session_id, token = _start_run(client)
    resp = client.post(f"/api/approve/{session_id}?token={token}", json={})
    assert resp.status_code == 409


def test_sessions_list_blocked_for_non_local(client):
    # TestClient requests originate from 'testserver', not localhost.
    assert client.get("/api/sessions?token=test-list-token").status_code == 403


def test_run_rejects_oversized_options(client):
    resp = client.post("/api/run", json={"idea": "ok", "tech_stack": "x" * 201})
    assert resp.status_code == 400
    assert "Tech stack" in resp.json()["error"]
    resp = client.post("/api/run", json={"idea": "ok", "security_framework": "x" * 201})
    assert resp.status_code == 400
    assert "Security framework" in resp.json()["error"]


def test_run_rejects_non_string_idea(client):
    resp = client.post("/api/run", json={"idea": 12345})
    assert resp.status_code == 400
    assert "idea" in resp.json()["error"]


def test_run_rejects_when_too_many_active_sprints(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "MAX_CONCURRENT_RUNS", 1)
    _start_run(client)
    resp = client.post("/api/run", json={"idea": "another sprint"})
    assert resp.status_code == 429
    assert "active sprints" in resp.json()["error"]


def test_approve_rejects_oversized_edit(client):
    from app.services.session_store import store

    session_id, token = _start_run(client)
    store.sessions[session_id]["status"] = "awaiting_approval"
    resp = client.post(
        f"/api/approve/{session_id}?token={token}",
        json={"edit": "x" * 20001},
    )
    assert resp.status_code == 400
    assert "20000 characters" in resp.json()["error"]


def test_session_access_via_bearer_header(client):
    session_id, token = _start_run(client)
    client.cookies.clear()  # force the header path
    resp = client.get(
        f"/api/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    resp = client.get(
        f"/api/sessions/{session_id}",
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 403


def test_pdf_export_after_completion(client):
    session_id, token = _start_run(client)
    from app.services.session_store import store

    store.sessions[session_id].update(
        status="complete",
        verdict="APPROVED",
        outputs={"business_analyst": "# Requirements\n- one\n- two"},
    )
    resp = client.get(f"/api/sessions/{session_id}/pdf?token={token}")
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"

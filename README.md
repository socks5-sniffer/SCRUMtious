# 🚀 SCRUMtious — AI-Powered Scrum Team Orchestration

> Transform any feature idea into a full sprint cycle — requirements, user story, implementation, security audit, and retrospective — in one pipeline.

Scrumtious is a standalone **web application** that orchestrates five specialised AI agents through a complete Agile sprint workflow. Give it any feature idea and it returns a production-ready artifact bundle while keeping a human in the loop between each stage.

Powered by [CrewAI](https://github.com/joaomdmoura/crewAI) · [Google Gemini](https://aistudio.google.com) · [FastAPI](https://fastapi.tiangolo.com) · Python 3.11+

[![CI](https://github.com/socks5-sniffer/SCRUMtious/actions/workflows/ci.yml/badge.svg)](https://github.com/socks5-sniffer/SCRUMtious/actions/workflows/ci.yml)
[![OWASP Top 10 Security Scan](https://github.com/socks5-sniffer/SCRUMtious/actions/workflows/owasp-security-scan.yml/badge.svg)](https://github.com/socks5-sniffer/SCRUMtious/actions/workflows/owasp-security-scan.yml)

---

## What It Does

1. You describe a feature idea in plain English.
2. Five AI agents collaborate sequentially — each building on the previous agent's output.
3. Every agent's work streams live to the UI as it completes.
4. You get a full artifact bundle: requirements doc, user story, code, security audit, and sprint retrospective — all downloadable as a single Markdown file.

![SCRUMtious UI](public/images/Screenshot%202026-05-09%20001530.png)

---

## The Agent Pipeline

```
Your Idea
    │
    ▼
┌─────────────────────────────────────────────────┐
│ 📋 Business Analyst                              │
│   • Identifies target personas                   │
│   • Writes user stories with acceptance criteria │
│   • Surfaces edge cases & hardware safety notes  │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│ 🎯 Product Owner                                 │
│   • Reviews and prioritises BA requirements      │
│   • Defines sprint scope & Definition of Done    │
│   • Flags hardware risks and dependencies        │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│ ⚡ Lead Developer                                │
│   • Implements idiomatic, commented source code  │
│   • Validates all inputs, no eval()/exec()       │
│   • Follows OWASP Secure Coding Practices        │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│ 🛡️ Security Auditor                              │
│   • Full OWASP Top-10 (2021) review              │
│   • Checks Principle of Least Privilege          │
│   • Emits APPROVED or BLOCKED verdict            │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│ 🔄 Scrum Master                                  │
│   • What went well / what was blocked            │
│   • ≥3 concrete process improvements             │
│   • Prioritised action items with owners         │
│   • Sprint goal verdict                          │
└─────────────────────────────────────────────────┘
    │
    ▼
📦 Download All Artifacts (.md bundle)
```

---

## Key Features

| Feature | Details |
|---|---|
| **Live streaming UI** | Agent progress streams via Server-Sent Events — no page reloads |
| **Human-in-the-loop** | Sprint pauses after each agent; review, optionally edit the output, then approve to continue |
| **Rendered markdown** | All agent output is rendered as rich HTML (headers, code blocks, tables) |
| **Tech stack selector** | Choose Python/gpiozero, FastAPI, Flask, Node.js, PHP, or Go before running |
| **Security framework selector** | OWASP Top-10, SANS Top-25, NIST 800-53, or CIS Controls |
| **Per-agent copy** | One-click clipboard copy of each agent's raw markdown output |
| **Download bundle** | Full sprint artifact bundle exported as a single `.md` file |
| **Session persistence** | Every sprint is saved to `sessions/<id>.json`; survives server restarts |
| **Session API** | `GET /api/sessions` lists all past runs; `GET /api/sessions/{id}` returns full outputs |
| **Error visibility** | Pipeline errors surface per-agent with a red error state in the UI |

---

## Project Structure

```
scrumtious/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.yml       # Bug report issue form
│   │   ├── config.yml           # Issue template configuration
│   │   └── feature_request.yml  # Feature request issue form
│   ├── workflows/
│   │   └── codeql.yml           # GitHub Actions CodeQL security analysis workflow
│   ├── dependabot.yml           # Dependabot update configuration
│   └── PULL_REQUEST_TEMPLATE.md # Pull request template
├── app/                         # FastAPI application package
│   ├── main.py                  # App factory (create_app) + ASGI `app`
│   ├── __main__.py              # `python -m app` dev-server entrypoint
│   ├── config.py                # Env loading, validation, and settings
│   ├── models.py                # Domain metadata (the agent roster)
│   ├── api/
│   │   └── routes.py            # FastAPI route handlers (thin HTTP layer)
│   ├── security/
│   │   ├── auth.py              # Per-session token validation / access control
│   │   ├── headers.py           # HTTP security-headers middleware (CSP, etc.)
│   │   └── rate_limit.py        # Per-client sliding-window rate limiter
│   └── services/
│       ├── session_store.py     # In-memory + JSON-file session persistence
│       ├── agent_prompts.py     # Declarative agent role/goal/task prompt specs
│       ├── crew_runner.py       # CrewAI orchestration + human-in-the-loop gate
│       └── pdf_export.py        # Branded A4 PDF generation
├── templates/
│   └── index.html               # Single-page UI markup (Jinja2)
├── static/                      # Static assets (served at /static)
│   ├── css/app.css              # UI styles
│   ├── js/app.js                # UI logic (vanilla JS, no inline scripts)
│   └── vendor/                  # Vendored marked + DOMPurify (no CDN)
├── public/                      # Images and other public-facing assets
├── sessions/                    # JSON session store (auto-created; gitignored)
├── data/
│   └── sprint-artifacts/        # Sample sprint output artifacts
├── .env                         # Your local secrets (never committed)
├── .env.example                 # Template for required environment variables
├── .gitignore
├── CODE_OF_CONDUCT.md           # Community standards and expectations
├── CONTRIBUTING.md              # Contribution guidelines
├── LICENSE
├── README.md
├── SECURITY.md                  # Security policy and reporting guidance
├── package-lock.json            # npm lockfile for frontend tooling/assets
└── requirements.txt            # Python dependencies
```

---

## Setup

### Prerequisites

- Python **3.11** or **3.12** (not 3.14 — CrewAI's dependency chain does not yet support it)
- A [Google AI Studio](https://aistudio.google.com/apikey) API key (Gemini)

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/socks5-sniffer/scrumtious.git
cd scrumtious

py -3.11 -m venv venv
# Windows
.\venv\Scripts\Activate.ps1
# macOS / Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Required — get yours at https://aistudio.google.com/apikey
GEMINI_API_KEY=your-gemini-api-key-here

# Optional — override the default model
# GEMINI_MODEL=gemini/gemini-2.0-flash

# Optional — Firebase project board sync
# FIREBASE_PROJECT_ID=your-firebase-project-id
# FIREBASE_SERVICE_ACCOUNT_KEY_PATH=/path/to/serviceAccountKey.json

# Optional — server binding
# HOST=127.0.0.1
# PORT=8000
```

### 4. Run

```bash
# Development server (auto-reload)
python -m app

# …or run the ASGI app directly with uvicorn
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000** in your browser.

---

## Usage

1. Type your feature idea in the text box (up to 2,000 characters).
2. Optionally select a **Language / Stack** and **Security Framework** from the dropdowns.
3. Press **Run Sprint** (or `Ctrl+Enter`).
4. Watch each agent card light up as it works — click any card to expand its output.
5. When complete, the **Sprint Retrospective** appears at the bottom with the security verdict badge.
6. Click **Download All Artifacts** to get a `.md` bundle of everything, or use the **Copy** button on any individual agent panel.

---

## Security Design

| Concern | Mitigation |
|---|---|
| API key exposure | Loaded from `.env` via `python-dotenv`; server refuses to start if `GEMINI_API_KEY` is missing |
| Firebase credentials | Service-account key file path stored in env var — file never committed |
| Code generation safety | Security Auditor agent blocks `eval()`, `exec()`, `shell=True`, bare `except` clauses |
| OWASP Top 10 | Explicitly checked in Security Auditor task for all 2021 categories |
| Principle of Least Privilege | Verified as a mandatory step in every audit |
| Input validation | Idea input capped at 2,000 characters server-side; `JSONResponse` enforces proper HTTP error codes |
| Session access control | `POST /api/run` issues a per-session token (HttpOnly cookie by default) required to stream, approve, and export that session |
| Session index access | `GET /api/sessions` is restricted to localhost and requires `SESSION_LIST_TOKEN` |
| Output rendering safety | Markdown is sanitized with DOMPurify before HTML rendering to reduce XSS risk |
| No hard-coded secrets | All keys loaded from environment; `.env` is in `.gitignore` |

---

## Architecture Notes

### `app/` — FastAPI application package

The backend is organised into focused modules under `app/` (see the project
structure above and [`docs/architecture.md`](docs/architecture.md) for the full
breakdown). Route handlers in `app/api/routes.py` stay thin and delegate to the
`app/services/*` modules for orchestration, persistence, and PDF export.

- Each sprint run creates a UUID-keyed session in an in-memory dict **and immediately writes it to `sessions/<id>.json`**.
- The CrewAI crew runs in a **background thread** (blocking I/O) so the async FastAPI event loop stays free.
- Agent progress is pushed to the session's event queue by a `task_callback` and consumed by the `/api/stream/{session_id}` SSE endpoint.
- **Human-in-the-loop**: after every agent (except the last) the background thread blocks on a `threading.Event`. The UI shows an approval panel; when the user clicks *Approve & Continue* (optionally after editing), the pipeline resumes.
- Approved edits are re-emitted as `agent_edited` SSE events so the UI updates the rendered output.
- `task_output.raw` is used to extract clean text from `TaskOutput` objects.
- Completed sessions persist to disk and are re-loaded into memory on startup.
- API endpoints: `GET /api/sessions`, `GET /api/sessions/{id}`, `POST /api/approve/{id}`.
- Protected session endpoints require a per-session token returned by `POST /api/run` (sent via HttpOnly cookie by default, with optional `token` query parameter support).

### `templates/index.html` — Single-page UI

- No framework — plain HTML, CSS custom properties, and vanilla JavaScript.
- `marked.js` (CDN) renders all agent output as HTML.
- `EventSource` drives the live feed; the connection stays open during HITL pauses and closes automatically when the session completes or errors.
- After each agent completes (except the Scrum Master), an **amber approval panel** slides open showing the agent's full output pre-filled into an edit textarea. The user can read, edit, and then continue the sprint.
- When the server confirms the approval, the `agent_start` SSE event for the next agent hides the panel automatically.
- `downloadArtifacts()` assembles a labelled Markdown document client-side and triggers a native download — no server roundtrip.

### `scrumtious.py` — Original CLI

The original standalone script includes an extended pipeline with a **remediation loop**: if the Security Auditor returns `BLOCKED`, the Lead Developer reworks the code and a re-audit runs before the Scrum Master retrospective is generated.

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | ✅ | — | Google Gemini API key |
| `GEMINI_MODEL` | No | `gemini/gemini-2.5-flash` | LiteLLM model string for CrewAI |
| `FIREBASE_PROJECT_ID` | No | — | Firebase project ID for board sync |
| `FIREBASE_SERVICE_ACCOUNT_KEY_PATH` | No | — | Path to Firebase service account JSON |
| `HOST` | No | `127.0.0.1` | Server bind address |
| `PORT` | No | `8000` | Server bind port |
| `SESSION_LIST_TOKEN` | No | — | Shared token required to call `GET /api/sessions` (in addition to localhost restriction) |
| `COOKIE_SECURE` | No | `0` | Set to `1` in HTTPS deployments to mark auth cookie as `Secure` |

---

## Roadmap

- [x] Human-in-the-loop approval gate between agents (with optional edits)
- [x] Session persistence (JSON file store in `sessions/`)
- [ ] PDF export of artifact bundle
- [ ] Custom agent configuration (add/remove/reorder agents)
- [ ] Firebase Firestore project board sync (live integration)
- [ ] Jira / GitHub Issues integration for artifact export
- [ ] Streaming token-by-token output (as Gemini emits tokens)

---

## Comparison

| Tool | BA → PO → Code | Security Audit | Retrospective | User-facing |
|---|---|---|---|---|
| **Scrumtious** | ✅ | ✅ | ✅ | ✅ |
| GitHub Copilot Workspace | Partial | ❌ | ❌ | ✅ |
| AutoGen / CrewAI / LangGraph | ✅ (DIY) | DIY | DIY | ❌ (framework) |
| Linear + AI | ❌ | ❌ | ❌ | ✅ |
| Jira AI | Partial | ❌ | ❌ | ✅ |

---

## License

MIT

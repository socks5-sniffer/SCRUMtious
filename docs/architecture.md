# Architecture

SCRUMtious is a single-process FastAPI application that orchestrates a five-agent
CrewAI pipeline and streams progress to a single-page UI. This document describes
the module layout introduced when the original `app.py` monolith was split, and
the deliberate tradeoffs behind the runtime design.

## Module layout

```
app/
├── main.py              # Application factory: create_app() wires everything together
├── __main__.py          # `python -m app` — runs the uvicorn dev server
├── config.py            # Environment loading, validation, and settings
├── models.py            # Domain metadata (the ordered agent roster)
├── api/
│   └── routes.py        # FastAPI route handlers — the thin HTTP layer
├── security/
│   ├── auth.py          # Per-session access-token validation
│   ├── headers.py       # HTTP security-headers middleware (CSP, X-Frame-Options, HSTS)
│   └── rate_limit.py    # Per-client sliding-window rate limiter
└── services/
    ├── session_store.py # In-memory session dict + JSON-file persistence
    ├── crew_runner.py   # CrewAI agents/tasks + human-in-the-loop gate
    └── pdf_export.py    # Branded A4 PDF rendering (markdown → HTML → PDF)
```

### Responsibilities and boundaries

- **`api/routes.py`** parses and validates requests, enforces auth and rate
  limits, and delegates everything else. It contains no orchestration or
  persistence logic.
- **`services/`** holds the domain logic. The route layer depends on services;
  services never import the route layer.
- **`security/`** is pure, framework-light helpers reused across routes and
  middleware.
- **`config.py`** is the single source of truth for environment-derived
  settings. Other modules import from it rather than calling `os.getenv`
  directly (the two runtime-mutable values — `GEMINI_API_KEY` and the optional
  `GEMINI_MODEL` override — are still read at call time in `crew_runner` so the
  process can pick up a rotated key without a restart).

### Entry points

- `uvicorn app.main:app` — the canonical ASGI entry point.
- `python -m app` — convenience wrapper that starts uvicorn with auto-reload.

`app.main.create_app()` is an application factory, so tests can build an isolated
app instance and the production server can be configured externally.

## Runtime design decisions

### Why a background thread for CrewAI work
`crew.kickoff()` is synchronous and blocking. Running it on the async event loop
would stall every other request. Each run is therefore executed on a daemon
`threading.Thread`, leaving the FastAPI event loop free to serve the SSE stream
and approval endpoints. Progress is communicated back to the request side through
the session's in-memory `events` list, which the `/api/stream/{id}` endpoint
polls and forwards as Server-Sent Events.

### Human-in-the-loop (HITL) gate
After every agent except the last, the worker thread blocks on a
`threading.Event` stored on the session. The UI shows an approval panel; the
`POST /api/approve/{id}` handler sets the event (optionally applying an edit),
which unblocks the thread and resumes the pipeline. CrewAI callback signatures
have changed across releases, so the task callback is wrapped defensively.

### Why in-memory + JSON-file session storage
Sessions live in a process-wide dict for fast access and to hold non-serialisable
state (the events queue and the HITL `Event`). Serialisable fields are mirrored
to `sessions/<id>.json` after every meaningful state change so completed runs
survive a restart and can be re-hydrated on startup. This keeps the app
dependency-free (no database) and easy to run locally.

## Limitations of the single-process model

- **No horizontal scaling.** The session store, rate limiter, and HITL events
  are all in-process. Running multiple uvicorn workers would split state across
  processes — a request could hit a worker that has never seen the session.
- **Thread-per-run concurrency.** Each active sprint holds a thread (often
  blocked on HITL approval). This is fine for modest concurrency but is not a
  job-queue.
- **At-most-once persistence.** A crash mid-run loses in-flight (non-persisted)
  events; a reloaded session is not resumable past the point it was interrupted.

### What multi-worker / production deployment would require

- Move session state to a shared store (e.g. Redis or a database).
- Replace the in-process rate limiter with a shared one (e.g. Redis-backed).
- Move sprint execution to a real task queue (e.g. Celery/RQ) with a durable
  broker, and drive HITL via persisted state rather than an in-memory `Event`.
- Run behind a reverse proxy (nginx/Caddy) terminating TLS; the app already sets
  HSTS when it sees an HTTPS scheme and emits a strict Content-Security-Policy.
  Set `TRUST_PROXY=1` so the app resolves client identity from the last
  `X-Forwarded-For` hop (the one your proxy appends). Without it the header is
  ignored — it is client-controlled — but then every connection appears to come
  from 127.0.0.1, which collapses the per-client rate limiter to a single bucket
  and makes the local-only `/api/sessions` gate treat all traffic as local.

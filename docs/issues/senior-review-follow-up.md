# Senior-review follow-up: improve maintainability, quality gates, and production readiness

## Summary
A senior-engineer style review of this repository found that the project already shows strong product thinking, unusually good repository hygiene, and solid security instincts for an early-stage project. The biggest gaps are maintainability, automated verification, and team-scale structure.

This issue tracks the highest-impact improvements to make the project easier to extend, safer to refactor, and more credible as a production-style codebase.

## Why this matters
Current strengths:
- Clear product concept and end-to-end implementation
- Strong README and open-source hygiene
- Security-conscious backend and frontend decisions
- Polished UI and good user workflow design

Primary weaknesses to address:
- Backend is too monolithic (`app.py` does too much)
- No visible automated tests
- No CI workflow for linting and tests
- Python dependencies are loosely pinned
- Architecture tradeoffs are not documented

## Recommended work

### 1. Break up `app.py` into maintainable modules
Refactor the current single-file backend into focused modules.

Possible structure:
- `app/main.py` — app creation and startup
- `app/api/routes.py` — FastAPI routes
- `app/services/session_store.py` — session persistence and retrieval
- `app/services/crew_runner.py` — CrewAI orchestration
- `app/services/pdf_export.py` — PDF generation
- `app/security/auth.py` — token validation and access control
- `app/models/` — request/response and internal models

**Definition of done**
- `app.py` is reduced to a minimal entrypoint or removed
- Core responsibilities are separated into modules with clear boundaries
- Route handlers no longer contain orchestration and persistence logic inline

### 2. Add automated tests
Add coverage for the most failure-prone and important flows.

Suggested initial coverage:
- Session token validation
- `POST /api/run`
- `POST /api/approve/{session_id}`
- `GET /api/stream/{session_id}`
- `GET /api/sessions/{session_id}` auth behavior
- PDF export behavior and failure handling
- Session persistence load/save logic

**Definition of done**
- A test suite exists and runs locally with one command
- Critical API routes have at least basic coverage
- Concurrency-sensitive logic is covered where practical

### 3. Add linting and type checking
Introduce lightweight quality gates.

Suggested tools:
- `ruff` for linting and formatting support
- `mypy` or `pyright` for type checking

**Definition of done**
- Linting command is documented in the README or CONTRIBUTING guide
- Type checking command is documented
- Repository passes both checks in CI

### 4. Add CI for lint + test
Create a GitHub Actions workflow that runs on push and pull request.

Suggested steps:
- Set up Python 3.11
- Install dependencies
- Run lint
- Run tests
- Optionally run type checks

**Definition of done**
- CI runs automatically on pushes and PRs
- Failing tests or lint errors block regressions from going unnoticed

### 5. Improve dependency management
Stabilize the Python environment.

Suggested improvements:
- Pin direct dependencies to tested versions
- Consider a lockfile or constraints file
- Document how dependency updates should be handled

**Definition of done**
- `requirements.txt` is pinned or backed by a constraints strategy
- Dependency update policy is documented

### 6. Document architecture and limitations
Add a short architecture section or separate `docs/architecture.md`.

Topics to document:
- Why the app uses a background thread for CrewAI work
- Why session data is stored in-memory + JSON files
- Current limitations of the single-process model
- What would need to change for multi-worker or production deployment

**Definition of done**
- Architecture and tradeoffs are explicitly documented
- Known limitations are easy for contributors to understand

## Nice-to-have follow-ups
- Add structured logging
- Introduce Pydantic models for request and response bodies
- Add frontend smoke tests for the HITL flow
- Separate domain logic from HTTP concerns more aggressively
- Add a deployment guide for local vs hosted usage

## Priority order
1. Add tests
2. Add CI
3. Split `app.py`
4. Add lint/type checks
5. Pin dependencies
6. Document architecture

## Notes
This is already a strong project for someone early in their development journey. These tasks are about turning a strong prototype into a more maintainable, team-friendly codebase.

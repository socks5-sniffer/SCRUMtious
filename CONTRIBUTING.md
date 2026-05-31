# Contributing to SCRUMtious

Thank you for your interest in contributing! This document covers everything you need to get started.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Branch & Commit Conventions](#branch--commit-conventions)
- [Pull Request Process](#pull-request-process)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)
- [Style Guidelines](#style-guidelines)

---

## Code of Conduct

This project follows our [Code of Conduct](CODE_OF_CONDUCT.md). By participating you agree to uphold it.

---

## How to Contribute

| Type | Where to start |
|------|---------------|
| Bug fix | Open an issue first (unless trivial), then a PR |
| New feature | Open a feature-request issue and discuss before coding |
| Docs | PRs welcome without a prior issue |
| Security | See [SECURITY.md](SECURITY.md) — **do not open a public issue** |

---

## Development Setup

### Prerequisites

- Python **3.11** or **3.12**
- Git
- A Google Gemini API key ([get one free](https://aistudio.google.com/apikey))

### Steps

```bash
# 1. Fork the repo on GitHub, then clone your fork
git clone https://github.com/<your-username>/SCRUMtious.git
cd SCRUMtious

# 2. Create a virtual environment
py -3.11 -m venv venv

# Windows
.\venv\Scripts\Activate.ps1
# macOS / Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY

# 5. Run the development server
python -m app
```

The app will be available at **http://127.0.0.1:8000**.

---

## Running Tests, Lint & Type Checks

Install the development dependencies, then run the suite:

```bash
pip install -r requirements.txt -r requirements-dev.txt

pytest             # run the test suite
ruff check app/    # lint
mypy app/ --ignore-missing-imports   # type check
```

The tests stub out the CrewAI call, so they run fast and require no API key
(a placeholder `GEMINI_API_KEY` is set automatically by the test fixtures).

The backend lives in the `app/` package — see
[`docs/architecture.md`](docs/architecture.md) for the module layout and design
tradeoffs.

---

## Branch & Commit Conventions

### Branches

Use the format `type/short-description`:

- `feat/pdf-export`
- `fix/sse-reconnect`
- `docs/contributing-guide`
- `chore/update-deps`

### Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add PDF export for artifact bundle
fix: prevent SSE connection leak on approval timeout
docs: update setup instructions for Python 3.12
chore: bump crewai to 0.x.x
```

---

## Pull Request Process

1. **Branch from `main`** — never commit directly to `main`.
2. **Keep PRs focused** — one logical change per PR makes review easier.
3. **Fill in the PR template** — describe what changed and why.
4. **Test manually** — run a full sprint to confirm nothing is broken.
5. **No secrets in commits** — double-check that `.env` is not staged.
6. A maintainer will review within a few days. Address feedback, then request re-review.
7. PRs are merged with **squash-and-merge** to keep the history clean.

---

## Reporting Bugs

Open a [Bug Report](https://github.com/socks5-sniffer/SCRUMtious/issues/new?template=bug_report.yml) and include:

- What you did
- What you expected to happen
- What actually happened
- Your OS, Python version, and browser
- Relevant logs from the terminal running `python -m app`

---

## Suggesting Features

Open a [Feature Request](https://github.com/socks5-sniffer/SCRUMtious/issues/new?template=feature_request.yml) and describe:

- The problem you are trying to solve
- Your proposed solution
- Any alternatives you considered

---

## Style Guidelines

- **Python**: follow [PEP 8](https://peps.python.org/pep-0008/). Keep functions small and clearly named.
- **No new dependencies** without discussion — the install footprint is deliberately small.
- **No hard-coded secrets** — all configuration via environment variables.
- **Security first** — any code that processes user input must validate it server-side.

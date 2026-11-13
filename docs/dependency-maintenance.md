# Dependency maintenance

The November 2, 2026 refresh started with static reads of dependency metadata and
OSV queries, before executing the old application or importing its dependencies.
The old environment had 24 Python packages with advisory matches, plus DOMPurify
3.4.13. Matches indicate affected package versions; they do not establish that
every vulnerable feature is reachable through this application.

## Reproduce the reviewed environment

Use a current Python 3.11 or 3.12 security patch release and a fresh virtual
environment. Python 3.12 is preferred. Do not copy packages from an older venv.

```sh
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# POSIX: source .venv/bin/activate
python -m pip install --upgrade pip
pip install --only-binary=:all: -r requirements.lock
```

`requirements.lock` includes the application, optional PDF renderer, development
tools, and transitive dependencies, with platform markers. For just the app use
`pip install --only-binary=:all: -c requirements.lock -r requirements.txt`; add
`-r requirements-pdf.txt` for PDF export. The lock pins versions rather than
artifact hashes. Wheels avoid executing source-package build hooks during setup.

## Review an update before running it

1. Read manifests, installed `*.dist-info/METADATA`, and vendored asset headers
   without importing the old packages. Check current upstream advisories and OSV.
2. Update the exact direct pins in the three requirements files. Use a reviewed,
   patched uv release to resolve the complete graph without source builds:

   ```sh
   uv pip compile requirements.txt requirements-pdf.txt requirements-dev.txt --universal --python-version 3.11 --only-binary=:all: --no-annotate --output-file requirements.lock
   ```

3. Audit the lock before installing it. `--disable-pip --no-deps` scans exact pins
   without invoking pip or installing the application:

   ```sh
   pip-audit --disable-pip --no-deps -r requirements.lock
   python scripts/audit_vendor.py
   ```

4. Install the reviewed lock into a fresh environment. Run `ruff check app/
   tests/ scripts/`, `mypy app/`, and `pytest`. Use placeholder API keys and an
   isolated `SESSIONS_DIR`; disable dotenv loading with
   `PYTHON_DOTENV_DISABLED=1` to keep tests away from local credentials.
5. Validate CrewAI imports and callbacks without making a provider request. A
   real Gemini sprint is a separate integration check that uses API quota.

CI fails on dependency-audit and medium/high Bandit findings. Vendor assets are
checked separately because the empty npm lockfile does not describe the browser
libraries actually served. When replacing a vendor file, update its exact version,
upstream URL, and SHA-256 in `static/vendor/manifest.json`; review both changes.
Network errors also fail the vendor audit, rather than reporting a clean result.

**Known upstream blocker:** the refreshed lock still includes `chromadb==1.5.9`
because CrewAI requires it. OSV lists four Chroma server/collection-management
advisories with no patched release: CVE-2026-45829, CVE-2026-45830,
CVE-2026-45831, and CVE-2026-45833. The dependency audit intentionally fails for
these findings; there is no blanket suppression. This app does not launch a
Chroma server, accept collection configuration, or enable CrewAI memory (now
explicitly `False`). Do not expose Chroma or enable remote-code/model-loading
features. A clean dependency audit remains blocked on an upstream fix or a
separately reviewed replacement of the orchestration dependency. See the
[pre-authentication code-injection advisory](https://github.com/advisories/GHSA-f4j7-r4q5-qw2c).

## Security findings and limits

- Starlette 1.0.0 was affected by Host-header/path confusion and Windows static
  file UNC-path credential disclosure, among other advisories. The direct pin
  now requires 1.10.0. See [upstream Windows advisory](https://github.com/Kludex/starlette/security/advisories/GHSA-wqp7-x3pw-xc5r).
- DOMPurify is updated to 3.4.17. Several intervening advisories concern opt-in
  configurations this app does not use, but keeping the sanitizer patched avoids
  relying on that distinction. See [upstream releases](https://github.com/cure53/DOMPurify/releases).
- The vendored marked parser is updated from 9.1.6 to 18.1.3. Its browser UMD
  bundle is extracted from the npm release after verifying the registry's SHA-512
  integrity value, without installing npm packages or executing lifecycle scripts.
- CrewAI is updated to 1.15.34, including newer transitive dependency floors.
  The app constructs its agents directly, does not load repository-supplied agent
  configurations, and enables no execution/scraping tools. Do not add these paths
  without reviewing [CVE-2026-92206](https://www.zerodayinitiative.com/advisories/ZDI-26-706/)
  and [the CrewAI tool advisories](https://kb.cert.org/vuls/id/221883).
- An audit checks known published vulnerabilities, not malicious-package
  provenance, all possible code vulnerabilities, or live-provider behavior.
- The existing Gemini 2.5 Flash default is deprecated. Google's current schedule
  routes it to Gemini 3.5 Flash-Lite on December 1, 2026; existing access and billing
  differ by account. Review [Google's schedule](https://ai.google.dev/gemini-api/docs/deprecations)
  and validate an explicit `GEMINI_MODEL` before migration.

## Local verification

On November 12, Markdown was updated to 3.11.3 and all 166 locked entries were
rechecked against OSV; ChromaDB remained the only affected package.

Validated on Windows using a new `.venv-modern` environment with Python 3.12.16;
the old `venv` was neither executed nor modified. The managed runtime is under
`.tools/python`; both directories are ignored by Git and must stay together.
Use `.venv-modern/Scripts/python.exe` for the refreshed local environment.

- Existing API, security, HITL, and PDF suites: **47 passed**.
- New installed-CrewAI compatibility test: **1 passed**, using real constructors,
  native Gemini provider configuration, event registration, and task callbacks,
  with kickoff replaced and socket connections blocked. Upstream deprecation and
  callback-checkpoint warnings remain; the app does not restore Crew checkpoints.
- Ruff: passed for `app/`, `tests/`, and `scripts/`.
- Mypy: passed for all 16 application modules.
- `uv pip check`: all 163 installed packages are compatible.
- OSV scan of all 166 universal lock entries: only ChromaDB remained affected
  (four advisories, with duplicate PYSEC aliases). This is **not** a clean audit.
- Both vendored JavaScript hashes and OSV checks passed.
- Marked UMD API checks passed for synchronous parsing, headings, GFM tables,
  fenced code blocks, and line breaks.
- `git diff --check`: passed.

No live Gemini request, public application server, Chroma server, deployment,
or remote CI run was started. Linux and Python 3.11 checks remain configured in
CI; local validation used Windows and Python 3.12.

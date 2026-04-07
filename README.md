# 🥒 scrumtious — AI-Driven Scrum Team Orchestration

> **picklePi** · Raspberry Pi GPIO education platform  
> Powered by [CrewAI](https://github.com/joaomdmoura/crewAI) · Python 3.10+

---

## Overview

`scrumtious.py` is a multi-agent orchestration script that simulates a complete Scrum team using CrewAI. Five specialised AI agents collaborate through a structured sprint workflow — from raw idea to retrospective — with a built-in security gate and optional Firebase sync for project board tracking.

The system is designed around the **picklePi** curriculum: an educational platform teaching Raspberry Pi GPIO programming and embedded-systems concepts to students, teachers, and makers.

---

## Agent Roster

| # | Agent | Role |
|---|-------|------|
| 1 | **Business Analyst** | Transforms raw feature ideas into structured, unambiguous requirements; writes user stories with acceptance criteria; surfaces edge cases before development begins |
| 2 | **Product Owner** | Manages the backlog; refines and prioritises sprint-ready user stories; keeps educational and security goals front-of-mind |
| 3 | **Lead Developer** | Implements Python 3 / PHP code for GPIO control and the picklePi web interface using strict secure-coding patterns |
| 4 | **Security Auditor** | Reviews all developer output against the OWASP Top 10 and Principle of Least Privilege; blocks unsafe artefacts before they progress |
| 5 | **Scrum Master** | Guards the Agile process; produces a structured sprint retrospective capturing blockers, wins, and next-sprint recommendations |

---

## Sprint Workflow

```
Raw Idea
   │
   ▼
[1] Business Analyst  ─── Structures requirements, writes user stories & acceptance criteria
   │
   ▼
[2] Product Owner     ─── Prioritises and finalises sprint-ready user story
   │
   ▼
[3] Lead Developer    ─── Implements secure Python 3 code (gpiozero, validated inputs)
   │
   ▼
[4] Security Auditor  ─── OWASP audit; emits APPROVED or BLOCKED verdict
   │
   ▼
[5] Scrum Master      ─── Sprint retrospective; process improvements; action items
   │
   ▼
Firebase Sync         ─── Project board snapshot written to Firestore (optional)
```

Each task receives the output of the previous task(s) as context, so every agent builds on the work of those upstream.

---

## Key Components

### `audit_code_for_violations(code)`

A lightweight static-analysis helper that scans code for two categories of findings before any artefact can be approved:

| Severity | Pattern | Reason |
|----------|---------|--------|
| `[BLOCK]` | `eval()` | Arbitrary code execution — CWE-95 |
| `[BLOCK]` | Bare `except:` clause | Swallows all errors silently — CWE-390 |
| `[WARN]` | `except Exception:` | Broad catch — should log or re-raise |

### `sync_project_board_to_firebase(project_board)`

Writes a structured sprint-board snapshot to Firebase Firestore at the end of each run. The snapshot includes:

- Project name and sprint number
- Per-task status and assigned agent
- Security audit verdict (`APPROVED` / `BLOCKED` / `UNKNOWN`)
- Raw crew output

> This is a **placeholder implementation**. Replace the body with `firebase_admin` calls once your Firebase project is provisioned.

### `_extract_verdict(audit_output)`

Parses the Security Auditor's free-text output to extract a clean `APPROVED` or `BLOCKED` verdict. Uses a two-pass strategy:

1. Looks for an explicit `Verdict: APPROVED/BLOCKED` line.
2. Falls back to finding the **last** occurrence of either keyword as a whole word (so a report that says "Initially BLOCKED … now APPROVED" resolves correctly).

### `_truncate(text, length)`

Clips long task descriptions to 80 characters for compact project-board storage.

---

## Setup

### 1. Clone & install dependencies

```bash
pip install -r requirements.txt
```

Core dependencies:

```
crewai
python-dotenv
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Then edit `.env`:

```env
# Required
OPENAI_API_KEY=sk-...

# Optional – only needed for Firebase sync
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_SERVICE_ACCOUNT_KEY_PATH=/path/to/serviceAccountKey.json
```

> **Security:** API keys are loaded exclusively from environment variables via `python-dotenv`. They are never hard-coded, logged, or committed to version control.

### 3. Run

```bash
python scrumtious.py
```

---

## Security Design

| Concern | Mitigation |
|---------|------------|
| API key exposure | Loaded from `.env` only; script aborts at startup if `OPENAI_API_KEY` is missing |
| Firebase credentials | Loaded from a service-account key file referenced by an env var — the file is never committed |
| Unsafe code generation | Security Auditor agent + `audit_code_for_violations()` block `eval()` and bare `except` |
| OWASP Top 10 | Security Auditor's task description explicitly checks all 2021 categories |
| Principle of Least Privilege | Verified as part of every security audit task |

---

## Output

After a successful run the script emits:

1. **Verbose agent logs** — each agent prints its reasoning to stdout.
2. **Sprint board** — a Python dict summarising every task, its agent, and overall status.
3. **Firebase sync** — the board is written to Firestore under `project_boards/picklePi` (when configured).
4. **Audit verdict** — logged at INFO level: `APPROVED`, `BLOCKED`, or `UNKNOWN`.

---

## Project Structure

```
Desktop/
├── scrumtious.py          # Original annotated source
├── scrumtious_clean.py    # Comment-free production version
├── .env                   # Local credentials (never commit)
├── .env.example           # Credentials template
└── requirements.txt       # Python dependencies
```

---

## License

MIT — see `LICENSE` for details.

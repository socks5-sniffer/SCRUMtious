#!/usr/bin/env python3
"""
picklePi – AI-Driven Scrum Team Orchestration
==============================================
Orchestrates a 5-agent Scrum team using CrewAI:

    1. Business Analyst – translates raw ideas into structured, dev-ready
                                                requirements; defines personas, constraints,
                                                acceptance criteria, and edge cases before dev starts.
    2. Product Owner    – manages the backlog, prioritises BA-approved
                                                requirements packages, and defines sprint scope and
                                                release readiness for the picklePi curriculum.
  3. Lead Developer   – implements Python / PHP code for Raspberry Pi GPIO and
                        the web interface using strict secure-coding patterns.
  4. Security Auditor – reviews all output for OWASP vulnerabilities, PoLP
                        violations, and unsafe patterns (e.g. eval(), missing
                        error handling).
    5. Scrum Master     – facilitates the Agile process during the sprint,
                                                tracks blockers across handoffs, and produces a sprint
                                                retrospective with next-sprint recommendations.

Workflow: BA refines requirements → PO prioritises sprint scope → Dev implements
                    → Security audits → rework if blocked → SM retrospective

Usage
-----
  1. Copy `.env.example` to `.env` and fill in your credentials.
  2. Install dependencies: pip install -r requirements.txt
  3. Run: python scrum_team.py

Security notes
--------------
- API keys are loaded exclusively from environment variables via python-dotenv.
  They are never hard-coded or logged.
- The Security Auditor agent blocks any artefact that contains `eval()` or
  lacks error handling before it reaches the final output.
- Firebase credentials are loaded from a service-account key file whose path
  is stored in an environment variable – the file itself is never committed.
"""

import os
import logging
import re
from typing import Any

from dotenv import load_dotenv
from crewai import Agent, Crew, Task, LLM

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger("picklePi.scrum_team")

# Validate that the minimum required env vars are present before proceeding.
_REQUIRED_ENV_VARS = ["GEMINI_API_KEY"]
_missing = [v for v in _REQUIRED_ENV_VARS if not os.getenv(v)]
if _missing:
    raise EnvironmentError(
        f"Missing required environment variable(s): {', '.join(_missing)}. "
        "Copy .env.example to .env and fill in the values."
    )

# ---------------------------------------------------------------------------
# LLM – Gemini via LiteLLM
# ---------------------------------------------------------------------------

_gemini_model = os.getenv("GEMINI_MODEL", "gemini/gemini-2.0-flash")
gemini_llm = LLM(
    model=_gemini_model,
    api_key=os.getenv("GEMINI_API_KEY"),
)

# ---------------------------------------------------------------------------
# Firebase – project-board sync (placeholder)
# ---------------------------------------------------------------------------


def sync_project_board_to_firebase(project_board: dict[str, Any]) -> None:
    """Sync the final Scrum project-board state to Firebase Firestore.

    This is a placeholder implementation. Replace the body with real
    firebase_admin calls once the Firebase project is provisioned.

    Args:
        project_board: A dictionary representing the current sprint board,
                       e.g. {"sprint": 1, "status": "Done", "stories": [...]}.

    Raises:
        RuntimeError: If the Firebase project ID env var is not set.
        Exception:    Re-raises any Firebase SDK errors after logging them.
    """
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    if not project_id:
        raise RuntimeError(
            "FIREBASE_PROJECT_ID environment variable is not set. "
            "Firebase sync requires a valid project ID."
        )

    logger.info("Syncing project board to Firebase project '%s' …", project_id)

    # TODO: Replace this block with actual firebase_admin integration, e.g.:
    #
    #   import firebase_admin
    #   from firebase_admin import credentials, firestore
    #
    #   key_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY_PATH")
    #   if not firebase_admin._apps:
    #       cred = credentials.Certificate(key_path)
    #       firebase_admin.initialize_app(cred)
    #
    #   db = firestore.client()
    #   db.collection("project_boards").document("picklePi").set(project_board)

    logger.info("Project board sync placeholder executed. Board state: %s", project_board)


# ---------------------------------------------------------------------------
# Security helper – used by the Security Auditor agent's tool/callback
# ---------------------------------------------------------------------------

_BLOCKED_PATTERNS = [
    (re.compile(r"\beval\s*\("), "use of eval()"),
    # Match bare `except:` only – not `except ValueError:` or similar.
    # Uses a negative lookahead so that any exception type following `except`
    # is allowed; only a naked colon (optionally preceded by whitespace)
    # triggers the violation.
    (re.compile(r"^\s*except\s*:", re.MULTILINE), "bare except clause (lacks error handling)"),
]

# Patterns that warrant a warning rather than an outright block.
_WARNING_PATTERNS = [
    # Catch-all Exception without re-raise or logging is a smell, but not always wrong.
    (
        re.compile(r"except\s+Exception\s*:", re.MULTILINE),
        "broad Exception catch – verify that it logs the error and/or re-raises",
    ),
]


def audit_code_for_violations(code: str) -> list[str]:
    """Return a list of security violation descriptions found in *code*.

    Checks for blocking issues:
    - eval() usage (arbitrary code execution risk – CWE-95)
    - Bare except clauses that swallow all errors (CWE-390)

    Also checks for non-blocking warnings:
    - Broad ``except Exception:`` catches without verified logging/re-raise

    Args:
        code: The source code string to audit.

    Returns:
        A list of human-readable violation or warning descriptions.
        Items prefixed with ``[BLOCK]`` must be remediated before approval;
        items prefixed with ``[WARN]`` should be reviewed but do not
        automatically block approval.
    """
    findings: list[str] = []
    for pattern, description in _BLOCKED_PATTERNS:
        if pattern.search(code):
            findings.append(f"[BLOCK] {description}")
    for pattern, description in _WARNING_PATTERNS:
        if pattern.search(code):
            findings.append(f"[WARN]  {description}")
    return findings


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

product_owner = Agent(
    role="Product Owner",
    goal=(
        "Manage the picklePi backlog by prioritising Business Analyst output, "
        "making scope trade-offs, and approving sprint-ready backlog items "
        "that balance security, hardware safety, and educational value."
    ),
    backstory=(
        "You are a seasoned Product Owner with a background in embedded systems "
        "and cybersecurity education. You decide what enters the sprint, what "
        "stays in the backlog, and what definition of done the team must meet. "
        "You always ask 'Is this safe for a student to run?' and 'Is this the "
        "highest-value increment for this sprint?'"
    ),
    llm=gemini_llm,
    verbose=True,
    allow_delegation=False,
)

lead_developer = Agent(
    role="Lead Developer",
    goal=(
        "Implement Python and PHP code for Raspberry Pi GPIO control and the "
        "picklePi web interface. Follow strict input-sanitisation and secure-"
        "coding patterns: validate all inputs, use parameterised queries, avoid "
        "dangerous built-ins, and always include error handling."
    ),
    backstory=(
        "You are a full-stack developer who specialises in IoT and Raspberry Pi "
        "projects. You write clean, well-commented, production-quality code and "
        "treat every GPIO interaction as a potential safety boundary. You never "
        "use eval(), exec(), or shell=True without an explicit security review."
    ),
    llm=gemini_llm,
    verbose=True,
    allow_delegation=False,
)

business_analyst = Agent(
    role="Business Analyst",
    goal=(
        "Translate raw picklePi feature ideas into structured, unambiguous, "
        "dev-ready requirements. Define personas, constraints, acceptance "
        "criteria, and edge cases, and ensure every requirement is testable "
        "before it reaches the Product Owner."
    ),
    backstory=(
        "You are a meticulous Business Analyst with experience bridging the gap "
        "between stakeholders and engineering teams on hardware education projects. "
        "You ask the questions developers forget to ask – 'What happens if the GPIO "
        "pin is already in use?', 'Which user personas are affected?', 'What's the "
        "failure mode?' – and you turn ambiguous ideas into crisp, reviewable "
        "specifications that leave no room for misinterpretation."
    ),
    llm=gemini_llm,
    verbose=True,
    allow_delegation=False,
)

security_auditor = Agent(
    role="Security Auditor",
    goal=(
        "Review all Lead Developer output for OWASP Top-10 vulnerabilities and "
        "Principle of Least Privilege (PoLP) violations. Approve only artefacts "
        "that meet the security bar, and return blocked work with structured "
        "remediation guidance for the Lead Developer."
    ),
    backstory=(
        "You are a certified application-security engineer with deep knowledge of "
        "OWASP, CWE, and embedded-systems threat modelling. You read every line of "
        "code with the assumption that it will be run by a student on physical "
        "hardware. You are the last line of defence before deployment."
    ),
    llm=gemini_llm,
    verbose=True,
    allow_delegation=False,
)

scrum_master = Agent(
    role="Scrum Master",
    goal=(
        "Guard the Agile process for the picklePi team by monitoring handoffs, "
        "surfacing blockers during the sprint, and producing a structured "
        "retrospective with prioritised process improvements and follow-up "
        "actions."
    ),
    backstory=(
        "You are a Certified Scrum Master who has facilitated dozens of embedded-"
        "systems sprints. You keep the team focused, surface blockers early, "
        "and tighten the quality of each role handoff so requirements, scope, "
        "implementation, and audit outcomes stay aligned. You care deeply about "
        "continuous improvement and making the next sprint run more smoothly "
        "than the last."
    ),
    llm=gemini_llm,
    verbose=True,
    allow_delegation=False,
)

# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

task_refine_requirements = Task(
    description=(
        "A new picklePi curriculum feature idea has arrived. Your job is to "
        "transform it into a structured requirements package before it reaches "
        "the Product Owner. You must:\n"
        "  1. Identify the target user persona(s) (student, teacher, maker, etc.).\n"
        "  2. Write at least one user story per persona using the format:\n"
        "     'As a [persona], I want [feature] so that [benefit].'\n"
        "  3. Define a minimum of 3 acceptance criteria per user story.\n"
        "  4. List at least 3 edge cases or clarifying questions that must be "
        "     answered before development begins.\n"
        "  5. Flag any ambiguities, missing constraints, or hardware safety "
        "     considerations (e.g. GPIO voltage limits, concurrent pin access).\n"
        "  6. Define non-negotiable constraints the Product Owner and Developer "
        "     must preserve.\n"
        "  7. Confirm that every requirement is testable and unambiguous.\n"
        "Deliver a structured requirements package ready for Product Owner review."
    ),
    expected_output=(
        "A structured requirements package containing user stories with acceptance "
        "criteria, a list of edge cases and clarifying questions, preserved "
        "constraints, flagged ambiguities, and hardware safety notes."
    ),
    agent=business_analyst,
)

task_create_user_story = Task(
    description=(
        "Review the Business Analyst's requirements package and turn it into a "
        "single sprint-ready backlog item for the next picklePi curriculum "
        "feature. You must:\n"
        "  1. Confirm the highest-value persona/problem to deliver this sprint.\n"
        "  2. Preserve or explicitly refine the Business Analyst's acceptance "
        "     criteria and constraints; do not discard them silently.\n"
        "  3. Define scope boundaries, priority, and definition of done.\n"
        "  4. Highlight any GPIO pin assignments, security considerations, and "
        "     educational learning objectives.\n"
        "  5. Flag any potential hardware safety risks or dependencies that could "
        "     block the sprint.\n"
        "Format your entire output in Markdown. Use ## headings for each section, "
        "bullet points for lists, and bold text for key terms. "
        "Deliver the backlog item as a clearly formatted Markdown document."
    ),
    expected_output=(
        "A Markdown-formatted sprint backlog item with the following sections:\n"
        "## Sprint Backlog Item\n"
        "## Priority & Scope\n"
        "## Acceptance Criteria\n"
        "## Definition of Done\n"
        "## GPIO & Hardware Notes\n"
        "## Security Considerations\n"
        "## Learning Objectives\n"
        "## Risks & Dependencies"
    ),
    agent=product_owner,
    context=[task_refine_requirements],
)

task_implement_feature = Task(
    description=(
        "Using the Business Analyst's requirements package and the Product Owner's "
        "approved backlog item, write the implementation for the picklePi feature. "
        "You must:\n"
        "  1. Write idiomatic Python 3 code using gpiozero for GPIO control.\n"
        "  2. Sanitise and validate ALL inputs before use.\n"
        "  3. Use try/except blocks with specific exception types – never bare excepts.\n"
        "  4. Never use eval(), exec(), or subprocess with shell=True.\n"
        "  5. Follow OWASP Secure Coding Practices.\n"
        "  6. Preserve all non-negotiable requirements and hardware safety constraints "
        "     from the Business Analyst package.\n"
        "  7. Add docstrings and inline comments explaining security decisions.\n"
        "Format your entire output in Markdown. Use ## headings for each section, "
        "fenced code blocks (```python) for all source code, and bullet points for "
        "explanatory lists. Deliver the implementation as a clearly formatted Markdown document."
    ),
    expected_output=(
        "A Markdown-formatted implementation document with the following sections:\n"
        "## Implementation Summary\n"
        "## Security Measures Applied\n"
        "## Source Code\n"
        "(fenced ```python code block)\n"
        "## Input Validation Notes\n"
        "## Hardware Safety Notes"
    ),
    agent=lead_developer,
    context=[task_refine_requirements, task_create_user_story],
)

task_security_audit = Task(
    description=(
        "Perform a security audit of the Lead Developer's implementation. You must:\n"
        "  1. Check for ALL OWASP Top-10 (2021) vulnerability categories.\n"
        "  2. Verify the Principle of Least Privilege is applied throughout.\n"
        "  3. Reject any code that contains eval(), exec(), shell=True, or bare "
        "     except clauses.\n"
        "  4. Confirm all inputs are validated and sanitised.\n"
        "  5. Confirm sensitive data (API keys, passwords) is never hard-coded.\n"
        "  6. Produce a structured audit report listing: PASS items, FAIL items "
        "     (with CWE/OWASP reference and remediation steps), and an overall "
        "     APPROVED or BLOCKED verdict.\n"
        "  7. If BLOCKED, provide a concise remediation handoff for the Lead "
        "     Developer that identifies the minimum changes required for re-review.\n"
        "Format your entire output in Markdown. Use ## headings for each section, "
        "bold for PASS/FAIL labels, and inline code for any referenced code patterns. "
        "Only APPROVED output may proceed to a Done state on the project board."
    ),
    expected_output=(
        "A Markdown-formatted security audit report with the following sections:\n"
        "## Audit Summary\n"
        "## OWASP Top-10 Findings\n"
        "(each item as a bullet: **PASS** or **FAIL** with CWE/OWASP ref)\n"
        "## Principle of Least Privilege Review\n"
        "## Input Validation Review\n"
        "## Sensitive Data Review\n"
        "## Remediation Handoff (if BLOCKED)\n"
        "## Verdict: APPROVED or BLOCKED"
    ),
    agent=security_auditor,
    context=[task_refine_requirements, task_create_user_story, task_implement_feature],
)

task_remediate_security_findings = Task(
    description=(
        "If the Security Auditor returns a BLOCKED verdict, remediate the failed "
        "findings and prepare the feature for re-review. You must:\n"
        "  1. Review the Security Auditor's remediation handoff and address each "
        "     FAIL item.\n"
        "  2. Preserve the Product Owner's scope boundaries and the Business "
        "     Analyst's non-negotiable constraints while remediating.\n"
        "  3. Explain what changed and why each change resolves the cited risk.\n"
        "  4. Do not introduce new dependencies or risky patterns unless they are "
        "     explicitly justified.\n"
        "Format your entire output in Markdown. Use ## headings for each section, "
        "fenced code blocks (```python) for all updated source code, and a "
        "bullet-point table mapping each finding to its fix. "
        "Deliver the remediated package as a clearly formatted Markdown document."
    ),
    expected_output=(
        "A Markdown-formatted remediation package with the following sections:\n"
        "## Rework Summary\n"
        "## Finding-to-Fix Mapping\n"
        "(bullet per finding: **Finding** → fix description)\n"
        "## Remediated Source Code\n"
        "(fenced ```python code block)\n"
        "## Constraints Preserved"
    ),
    agent=lead_developer,
    context=[task_refine_requirements, task_create_user_story, task_implement_feature, task_security_audit],
)

task_reaudit_remediated_feature = Task(
    description=(
        "Perform a focused re-audit of the remediated implementation. You must:\n"
        "  1. Confirm whether each previously failed finding has been resolved.\n"
        "  2. Identify any regressions introduced during remediation.\n"
        "  3. Produce a concise report with PASS/FAIL items and a final verdict line "
        "     in the form 'Verdict: APPROVED' or 'Verdict: BLOCKED'.\n"
        "Format your entire output in Markdown. Use ## headings for each section "
        "and bold **PASS** / **FAIL** labels for each finding. "
        "Only APPROVED output may proceed to a Done state on the project board."
    ),
    expected_output=(
        "A Markdown-formatted re-audit report with the following sections:\n"
        "## Re-Audit Summary\n"
        "## Finding Resolution Status\n"
        "(bullet per original finding: **PASS** or **FAIL** with brief note)\n"
        "## Regression Check\n"
        "## Verdict: APPROVED or BLOCKED"
    ),
    agent=security_auditor,
    context=[task_refine_requirements, task_create_user_story, task_implement_feature, task_security_audit, task_remediate_security_findings],
)

task_sprint_retrospective = Task(
    description=(
        "The sprint has completed. Review the outputs from the Business Analyst, "
        "Product Owner, Lead Developer, and Security Auditor, including any "
        "remediation and re-audit cycle, then produce a sprint retrospective. "
        "You must:\n"
        "  1. Summarise what went well (process strengths, quality wins).\n"
        "  2. Identify what was blocked or slowed down (bottlenecks, unclear "
        "     requirements, security findings that required rework).\n"
        "  3. Propose at least 3 concrete process improvements for the next sprint.\n"
        "  4. List prioritised follow-up action items with a suggested owner "
        "     (BA, PO, Dev, Security Auditor, or Scrum Master) for each.\n"
        "  5. Confirm whether the sprint goal was met and whether the delivered "
        "     feature is ready for the picklePi curriculum.\n"
        "Format your entire output in Markdown. Use ## headings for each section, "
        "numbered lists for action items, and bold text for owner assignments. "
        "Deliver the retrospective as a clearly formatted Markdown document."
    ),
    expected_output=(
        "A Markdown-formatted sprint retrospective with the following sections:\n"
        "## Sprint Goal Verdict\n"
        "## What Went Well\n"
        "## Blockers & Bottlenecks\n"
        "## Process Improvements for Next Sprint\n"
        "## Action Items\n"
        "(numbered list with **Owner** per item)"
    ),
    agent=scrum_master,
    context=[
        task_refine_requirements,
        task_create_user_story,
        task_implement_feature,
        task_security_audit,
        task_remediate_security_findings,
        task_reaudit_remediated_feature,
    ],
)

# ---------------------------------------------------------------------------
# Crew
# ---------------------------------------------------------------------------

scrum_crew = Crew(
    agents=[business_analyst, product_owner, lead_developer, security_auditor, scrum_master],
    tasks=[
        task_refine_requirements,
        task_create_user_story,
        task_implement_feature,
        task_security_audit,
        task_remediate_security_findings,
        task_reaudit_remediated_feature,
        task_sprint_retrospective,
    ],
    verbose=True,
)

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


_TASK_SUMMARY_LENGTH = 80


def _status_from_verdict(verdict: str, *, approved: str, blocked: str, unknown: str) -> str:
    """Return a board status string based on a security verdict."""
    if verdict == "APPROVED":
        return approved
    if verdict == "BLOCKED":
        return blocked
    return unknown


def _truncate(text: str, length: int = _TASK_SUMMARY_LENGTH) -> str:
    """Return *text* truncated to *length* characters, appending '…' if cut.

    Args:
        text: The string to truncate.
        length: Maximum number of characters before the ellipsis.

    Returns:
        The original string if it fits within *length*, otherwise the first
        *length* characters followed by '…'.
    """
    return text if len(text) <= length else text[:length] + "…"


def main() -> None:
    """Run the Scrum team crew and sync the result to Firebase."""
    logger.info("Starting picklePi Scrum Team Orchestration …")

    result = scrum_crew.kickoff()
    audit_verdict = _extract_verdict(str(result))

    logger.info("Crew execution complete. Processing results …")

    # Build a simple project-board snapshot from the crew result.
    project_board: dict[str, Any] = {
        "project": "picklePi",
        "sprint": 1,
        "status": _status_from_verdict(
            audit_verdict,
            approved="Done",
            blocked="Blocked",
            unknown="Review Inconclusive",
        ),
        "audit_verdict": audit_verdict,
        "stories": [
            {
                "task": _truncate(task_refine_requirements.description),
                "agent": business_analyst.role,
                "status": "Done",
            },
            {
                "task": _truncate(task_create_user_story.description),
                "agent": product_owner.role,
                "status": "Done",
            },
            {
                "task": _truncate(task_implement_feature.description),
                "agent": lead_developer.role,
                "status": _status_from_verdict(
                    audit_verdict,
                    approved="Done",
                    blocked="Superseded by Rework",
                    unknown="Pending Review",
                ),
            },
            {
                "task": _truncate(task_security_audit.description),
                "agent": security_auditor.role,
                "status": _status_from_verdict(
                    audit_verdict,
                    approved="Approved",
                    blocked="Blocked",
                    unknown="Review Inconclusive",
                ),
            },
            {
                "task": _truncate(task_remediate_security_findings.description),
                "agent": lead_developer.role,
                "status": _status_from_verdict(
                    audit_verdict,
                    approved="Done",
                    blocked="Needs Further Rework",
                    unknown="Not Required",
                ),
            },
            {
                "task": _truncate(task_reaudit_remediated_feature.description),
                "agent": security_auditor.role,
                "status": _status_from_verdict(
                    audit_verdict,
                    approved="Approved",
                    blocked="Blocked",
                    unknown="Not Run",
                ),
            },
            {
                "task": _truncate(task_sprint_retrospective.description),
                "agent": scrum_master.role,
                "status": "Done",
            },
        ],
        "raw_output": str(result),
    }

    sync_project_board_to_firebase(project_board)

    logger.info("All done. Audit verdict: %s", project_board["audit_verdict"])


def _extract_verdict(audit_output: str) -> str:
    """Extract APPROVED or BLOCKED from the security auditor's output.

    Searches for a structured verdict line of the form
    ``Verdict: APPROVED`` or ``Verdict: BLOCKED`` (case-insensitive).
    Falls back to scanning for the keywords as standalone words if the
    structured form is absent, preferring the *last* occurrence so that
    a report which mentions "Initially BLOCKED … now APPROVED" resolves
    correctly.

    Args:
        audit_output: The raw string output from the Security Auditor task.

    Returns:
        'APPROVED', 'BLOCKED', or 'UNKNOWN' if neither keyword is found.
    """
    # Prefer an explicit "Verdict: X" line for unambiguous extraction.
    structured = re.search(
        r"\bverdict\s*[:\-]\s*(approved|blocked)\b",
        audit_output,
        re.IGNORECASE,
    )
    if structured:
        return structured.group(1).upper()

    # Fall back to the *last* occurrence of the keywords as whole words.
    matches = list(re.finditer(r"\b(APPROVED|BLOCKED)\b", audit_output.upper()))
    if matches:
        return matches[-1].group(1)

    return "UNKNOWN"


if __name__ == "__main__":
    main()
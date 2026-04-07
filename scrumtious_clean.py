import os
import logging
import re
from typing import Any

from dotenv import load_dotenv
from crewai import Agent, Crew, Task

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger("picklePi.scrum_team")

_REQUIRED_ENV_VARS = ["OPENAI_API_KEY"]
_missing = [v for v in _REQUIRED_ENV_VARS if not os.getenv(v)]
if _missing:
    raise EnvironmentError(
        f"Missing required environment variable(s): {', '.join(_missing)}. "
        "Copy scrum_team/.env.example to scrum_team/.env and fill in the values."
    )


def sync_project_board_to_firebase(project_board: dict[str, Any]) -> None:
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    if not project_id:
        raise RuntimeError(
            "FIREBASE_PROJECT_ID environment variable is not set. "
            "Firebase sync requires a valid project ID."
        )

    logger.info("Syncing project board to Firebase project '%s' …", project_id)

    logger.info("Project board sync placeholder executed. Board state: %s", project_board)


_BLOCKED_PATTERNS = [
    (re.compile(r"\beval\s*\("), "use of eval()"),
    (re.compile(r"^\s*except\s*:", re.MULTILINE), "bare except clause (lacks error handling)"),
]

_WARNING_PATTERNS = [
    (
        re.compile(r"except\s+Exception\s*:", re.MULTILINE),
        "broad Exception catch – verify that it logs the error and/or re-raises",
    ),
]


def audit_code_for_violations(code: str) -> list[str]:
    findings: list[str] = []
    for pattern, description in _BLOCKED_PATTERNS:
        if pattern.search(code):
            findings.append(f"[BLOCK] {description}")
    for pattern, description in _WARNING_PATTERNS:
        if pattern.search(code):
            findings.append(f"[WARN]  {description}")
    return findings


product_owner = Agent(
    role="Product Owner",
    goal=(
        "Manage the picklePi backlog and define clear, actionable technical "
        "user stories that prioritise security best practices and hardware "
        "educational value for Raspberry Pi GPIO projects."
    ),
    backstory=(
        "You are a seasoned Product Owner with a background in embedded systems "
        "and cybersecurity education. You translate high-level picklePi goals "
        "into sprint-ready user stories, always asking 'Is this safe for a "
        "student to run?' and 'Does this teach a lasting hardware principle?'"
    ),
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
    verbose=True,
    allow_delegation=False,
)

business_analyst = Agent(
    role="Business Analyst",
    goal=(
        "Translate raw picklePi feature ideas into structured, unambiguous, "
        "dev-ready requirements. Write clear user stories with acceptance criteria, "
        "identify edge cases, and ensure every requirement is testable and "
        "actionable before it reaches the Product Owner or Developer."
    ),
    backstory=(
        "You are a meticulous Business Analyst with experience bridging the gap "
        "between stakeholders and engineering teams on hardware education projects. "
        "You ask the questions developers forget to ask – 'What happens if the GPIO "
        "pin is already in use?', 'Which user personas are affected?', 'What's the "
        "failure mode?' – and you turn ambiguous ideas into crisp, reviewable "
        "specifications that leave no room for misinterpretation."
    ),
    verbose=True,
    allow_delegation=False,
)

security_auditor = Agent(
    role="Security Auditor",
    goal=(
        "Review all Lead Developer output for OWASP Top-10 vulnerabilities and "
        "Principle of Least Privilege (PoLP) violations. Block any artefact that "
        "contains eval(), lacks error handling, or exposes sensitive data. Provide "
        "a structured remediation report for every finding."
    ),
    backstory=(
        "You are a certified application-security engineer with deep knowledge of "
        "OWASP, CWE, and embedded-systems threat modelling. You read every line of "
        "code with the assumption that it will be run by a student on physical "
        "hardware. You are the last line of defence before deployment."
    ),
    verbose=True,
    allow_delegation=False,
)

scrum_master = Agent(
    role="Scrum Master",
    goal=(
        "Guard the Agile process for the picklePi team. After each sprint, produce "
        "a structured retrospective that captures what went well, what was blocked, "
        "process improvements for the next sprint, and a prioritised list of "
        "follow-up actions."
    ),
    backstory=(
        "You are a Certified Scrum Master who has facilitated dozens of embedded-"
        "systems sprints. You keep the team focused, surface blockers early, and "
        "ensure every sprint ends with actionable retrospective notes. You care "
        "deeply about continuous improvement and making the next sprint run more "
        "smoothly than the last."
    ),
    verbose=True,
    allow_delegation=False,
)

task_refine_requirements = Task(
    description=(
        "A new picklePi curriculum feature idea has arrived. Your job is to "
        "transform it into a structured requirements document before it reaches "
        "the Product Owner. You must:\n"
        "  1. Identify the target user persona(s) (student, teacher, maker, etc.).\n"
        "  2. Write at least one user story per persona using the format:\n"
        "     'As a [persona], I want [feature] so that [benefit].'\n"
        "  3. Define a minimum of 3 acceptance criteria per user story.\n"
        "  4. List at least 3 edge cases or clarifying questions that must be "
        "     answered before development begins.\n"
        "  5. Flag any ambiguities, missing constraints, or hardware safety "
        "     considerations (e.g. GPIO voltage limits, concurrent pin access).\n"
        "  6. Confirm that every requirement is testable and unambiguous.\n"
        "Deliver a structured requirements document ready for Product Owner review."
    ),
    expected_output=(
        "A structured requirements document containing user stories with acceptance "
        "criteria, a list of edge cases and clarifying questions, flagged "
        "ambiguities, and hardware safety notes."
    ),
    agent=business_analyst,
)

task_create_user_story = Task(
    description=(
        "Create a detailed, sprint-ready user story for the next picklePi "
        "curriculum feature. The story must:\n"
        "  1. Follow the format: 'As a [persona], I want [feature] so that [benefit].'\n"
        "  2. Include clear acceptance criteria (minimum 3).\n"
        "  3. Highlight any GPIO pin assignments, security considerations, and "
        "     educational learning objectives.\n"
        "  4. Flag any potential hardware safety risks.\n"
        "Deliver the user story as a structured text block."
    ),
    expected_output=(
        "A complete user story with title, description, acceptance criteria, "
        "GPIO details, security notes, and learning objectives."
    ),
    agent=product_owner,
    context=[task_refine_requirements],
)

task_implement_feature = Task(
    description=(
        "Using the user story produced by the Product Owner, write the implementation "
        "for the picklePi feature. You must:\n"
        "  1. Write idiomatic Python 3 code using gpiozero for GPIO control.\n"
        "  2. Sanitise and validate ALL inputs before use.\n"
        "  3. Use try/except blocks with specific exception types – never bare excepts.\n"
        "  4. Never use eval(), exec(), or subprocess with shell=True.\n"
        "  5. Follow OWASP Secure Coding Practices.\n"
        "  6. Add docstrings and inline comments explaining security decisions.\n"
        "Deliver the complete, runnable source file(s) with a brief explanation."
    ),
    expected_output=(
        "Complete, commented Python 3 source code that implements the user story, "
        "together with a short explanation of the security measures applied."
    ),
    agent=lead_developer,
    context=[task_create_user_story],
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
        "Only APPROVED output may proceed to the project board."
    ),
    expected_output=(
        "A structured security audit report with individual findings (PASS/FAIL), "
        "CWE/OWASP references, remediation guidance, and a final APPROVED or "
        "BLOCKED verdict."
    ),
    agent=security_auditor,
    context=[task_implement_feature],
)

task_sprint_retrospective = Task(
    description=(
        "The sprint has completed. Review the outputs from the Business Analyst, "
        "Product Owner, Lead Developer, and Security Auditor, then produce a "
        "sprint retrospective. You must:\n"
        "  1. Summarise what went well (process strengths, quality wins).\n"
        "  2. Identify what was blocked or slowed down (bottlenecks, unclear "
        "     requirements, security findings that required rework).\n"
        "  3. Propose at least 3 concrete process improvements for the next sprint.\n"
        "  4. List prioritised follow-up action items with a suggested owner "
        "     (BA, PO, Dev, or Security Auditor) for each.\n"
        "  5. Confirm whether the sprint goal was met and whether the delivered "
        "     feature is ready for the picklePi curriculum.\n"
        "Deliver the retrospective as a structured, actionable report."
    ),
    expected_output=(
        "A structured sprint retrospective report with sections for: went well, "
        "blockers, process improvements, prioritised action items (with owners), "
        "and a sprint-goal verdict."
    ),
    agent=scrum_master,
    context=[task_refine_requirements, task_create_user_story, task_implement_feature, task_security_audit],
)

scrum_crew = Crew(
    agents=[business_analyst, product_owner, lead_developer, security_auditor, scrum_master],
    tasks=[
        task_refine_requirements,
        task_create_user_story,
        task_implement_feature,
        task_security_audit,
        task_sprint_retrospective,
    ],
    verbose=True,
)

_TASK_SUMMARY_LENGTH = 80


def _truncate(text: str, length: int = _TASK_SUMMARY_LENGTH) -> str:
    return text if len(text) <= length else text[:length] + "…"


def main() -> None:
    logger.info("Starting picklePi Scrum Team Orchestration …")

    result = scrum_crew.kickoff()

    logger.info("Crew execution complete. Processing results …")

    project_board: dict[str, Any] = {
        "project": "picklePi",
        "sprint": 1,
        "status": "Done",
        "audit_verdict": _extract_verdict(str(result)),
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
                "status": "Done",
            },
            {
                "task": _truncate(task_security_audit.description),
                "agent": security_auditor.role,
                "status": "Done",
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
    structured = re.search(
        r"\bverdict\s*[:\-]\s*(approved|blocked)\b",
        audit_output,
        re.IGNORECASE,
    )
    if structured:
        return structured.group(1).upper()

    matches = list(re.finditer(r"\b(APPROVED|BLOCKED)\b", audit_output.upper()))
    if matches:
        return matches[-1].group(1)

    return "UNKNOWN"


if __name__ == "__main__":
    main()

# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| `main` branch | ✅ |
| Older tags | ❌ |

Only the latest commit on `main` receives security fixes.

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities privately via **[GitHub Private Security Advisories](https://github.com/socks5-sniffer/SCRUMtious/security/advisories/new)**.

Include as much of the following as possible:

- A clear description of the vulnerability and its potential impact
- Steps to reproduce (proof-of-concept code or curl commands are helpful)
- Affected file(s) and line numbers if known
- Any suggested mitigations

### What to expect

| Timeline | Action |
|----------|--------|
| **72 hours** | Acknowledgement of your report |
| **7 days** | Initial assessment and severity triage |
| **30 days** | Target resolution for high/critical issues |

You will be credited in the release notes unless you prefer to remain anonymous.

## Scope

The following are **in scope**:

- The FastAPI server (`app.py`) — SSE endpoints, session handling, input validation
- Dependency vulnerabilities in `requirements.txt`
- Secrets or API key leakage
- Server-Side Request Forgery (SSRF) via AI agent output
- Prompt injection leading to data exfiltration

The following are **out of scope**:

- Vulnerabilities in third-party services (Google Gemini, CrewAI) — report those upstream
- Theoretical attacks with no practical exploit path
- Issues already documented as known limitations in the README

## Security Best Practices for Deployments

- Never commit `.env` — it is gitignored by default
- Run the server behind a reverse proxy (e.g. nginx) with TLS in any non-local deployment
- Restrict `HOST` to `127.0.0.1` unless you intend to expose the service on a network
- Rotate your `GEMINI_API_KEY` if it is ever inadvertently exposed

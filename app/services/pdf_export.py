"""Branded A4 PDF export for completed sprint sessions.

Renders each agent's Markdown output to HTML (``markdown``) and the assembled
document to PDF (``xhtml2pdf``/ReportLab). No shell calls, no temp files, no
eval — everything runs in-process.
"""

import io
from html import escape

_AGENT_PDF_META = [
    ("business_analyst", "Business Analyst",  "#6366f1", "Requirements Document"),
    ("product_owner",    "Product Owner",     "#8b5cf6", "User Story & Backlog"),
    ("lead_developer",   "Lead Developer",    "#06b6d4", "Implementation"),
    ("security_auditor", "Security Auditor",  "#f59e0b", "Audit Report"),
    ("scrum_master",     "Scrum Master",      "#10b981", "Sprint Retrospective"),
]


def _reject_external_resources(uri: str, rel: str | None = None) -> str:
    """xhtml2pdf link callback that blocks all external resource loading.

    The report is fully self-contained (inline CSS, no images), so any resource
    reference — typically an ``<img>`` smuggled in via LLM/user Markdown — is
    treated as hostile. Refusing to resolve ``http(s)://``, ``file://`` and
    local filesystem paths prevents SSRF and local file disclosure during the
    server-side render. ``data:`` URIs are inline and harmless, so they pass.
    """
    if uri.startswith("data:"):
        return uri
    raise ValueError(f"Blocked external resource during PDF render: {uri!r}")


def build_sprint_pdf(session: dict) -> bytes:
    """Render a branded A4 PDF from a completed session's agent outputs."""
    import markdown as md_lib
    from xhtml2pdf import pisa

    # User-/LLM-supplied metadata is escaped before being interpolated into the
    # HTML template to prevent HTML injection in the generated PDF.
    idea               = escape(session.get("idea", ""))
    tech_stack         = escape(session.get("tech_stack", ""))
    security_framework = escape(session.get("security_framework", ""))
    created_at         = escape(session.get("created_at", ""))
    verdict            = escape((session.get("verdict") or "UNKNOWN").upper())
    outputs            = session.get("outputs", {})

    verdict_color = {"APPROVED": "#10b981", "BLOCKED": "#ef4444"}.get(verdict, "#f59e0b")

    # Build one HTML section per agent
    sections_html = ""
    for agent_id, label, color, subtitle in _AGENT_PDF_META:
        content = outputs.get(agent_id, "")
        if not content:
            continue
        content_html = md_lib.markdown(content, extensions=["fenced_code", "tables"])
        sections_html += f"""
        <div class="section">
            <div class="section-header" style="border-left:5px solid {color};">
                <span class="section-role" style="color:{color};">{label}</span>
                <span class="section-subtitle">{subtitle}</span>
            </div>
            <div class="section-body">{content_html}</div>
        </div>
        """

    meta_rows = f"<tr><td><b>Idea</b></td><td>{idea}</td></tr>"
    if tech_stack:
        meta_rows += f"<tr><td><b>Tech Stack</b></td><td>{tech_stack}</td></tr>"
    if security_framework:
        meta_rows += f"<tr><td><b>Security Framework</b></td><td>{security_framework}</td></tr>"
    meta_rows += f"<tr><td><b>Generated (UTC)</b></td><td>{created_at}</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><style>
  @page {{ size: A4; margin: 20mm 18mm 20mm 18mm; }}
  body {{ font-family: Helvetica, Arial, sans-serif; font-size: 10pt; color: #1a1a2e; line-height: 1.55; }}
  .cover {{ text-align: center; padding: 36px 0 28px; border-bottom: 3px solid #6366f1; margin-bottom: 22px; }}
  .cover-title {{ font-size: 26pt; color: #6366f1; font-weight: bold; margin: 0 0 4px; }}
  .cover-sub   {{ font-size: 11pt; color: #555; margin-bottom: 14px; }}
  .verdict-pill {{ display: inline-block; padding: 4px 16px; border-radius: 20px;
                   font-size: 10pt; font-weight: bold; color: #fff; background: {verdict_color}; }}
  .meta-table  {{ width: 100%; border-collapse: collapse; font-size: 9pt; margin: 12px 0 0; }}
  .meta-table td {{ padding: 4px 8px; vertical-align: top; }}
  .meta-table td:first-child {{ width: 160px; color: #555; }}
  .section {{ margin-bottom: 22px; page-break-inside: avoid; }}
  .section-header {{ padding: 8px 12px; background: #f7f7fc; margin-bottom: 8px; }}
  .section-role    {{ font-size: 12pt; font-weight: bold; display: block; }}
  .section-subtitle{{ font-size: 9pt; color: #888; }}
  .section-body    {{ padding: 0 4px; font-size: 9.5pt; }}
  .section-body h1,.section-body h2 {{ font-size: 11pt; color: #1a1a2e; margin: 10px 0 4px; }}
  .section-body h3,.section-body h4 {{ font-size: 10pt; color: #333; margin: 8px 0 3px; }}
  .section-body p  {{ margin: 4px 0 8px; }}
  .section-body ul,.section-body ol {{ margin: 4px 0 8px 18px; }}
  .section-body li {{ margin-bottom: 3px; }}
  .section-body code {{ background: #f0f0f5; padding: 1px 4px; border-radius: 3px;
                        font-size: 8.5pt; font-family: Courier, monospace; }}
  .section-body pre  {{ background: #f0f0f5; padding: 8px; border-radius: 4px; font-size: 8pt; }}
  .section-body table {{ border-collapse: collapse; width: 100%; font-size: 9pt; }}
  .section-body th {{ background: #f0f0f5; padding: 4px 8px; text-align: left; }}
  .section-body td {{ padding: 3px 8px; border-bottom: 1px solid #e0e0e8; }}
  .footer {{ text-align: center; font-size: 8pt; color: #aaa;
             margin-top: 28px; border-top: 1px solid #e0e0e8; padding-top: 8px; }}
</style></head>
<body>
  <div class="cover">
    <div class="cover-title">SCRUMtious</div>
    <div class="cover-sub">AI Scrum Team Sprint Report</div>
    <span class="verdict-pill">{verdict}</span>
    <table class="meta-table">{meta_rows}</table>
  </div>
  {sections_html}
  <div class="footer">Generated by SCRUMtious &middot; AI-powered Scrum Team Orchestration</div>
</body></html>"""

    buf = io.BytesIO()
    result = pisa.CreatePDF(html, dest=buf, link_callback=_reject_external_resources)
    if getattr(result, "err", 0):
        raise RuntimeError(f"PDF generation encountered {getattr(result, 'err', '?')} error(s)")
    return buf.getvalue()

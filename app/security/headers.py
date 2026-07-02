"""HTTP security headers middleware.

Applies a strict set of response headers (CSP, X-Frame-Options, etc.) to every
response, plus HSTS when served over HTTPS.
"""

from fastapi import FastAPI, Request

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; "
        # Scripts are vendored into /static and wired via addEventListener, so
        # no CDN host and no 'unsafe-inline' — the Markdown sanitizer cannot be
        # replaced by a third party or an injected inline script.
        "script-src 'self'; "
        # Fonts are self-hosted too (static/fonts), so no external hosts at all:
        # every resource the page loads comes from this origin.
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'"
    ),
}


def add_security_headers(app: FastAPI) -> None:
    """Register the security-headers middleware on the given app."""

    @app.middleware("http")
    async def set_security_headers(request: Request, call_next):
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

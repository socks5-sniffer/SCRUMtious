"""Token validation and access control helpers.

Each session is protected by a per-session ``access_token`` (also set as an
httponly cookie). These helpers perform constant-time comparison and resolve the
token from either the query string or the cookie.
"""

import hmac
from typing import Any

from fastapi import Request


def is_local_request(request: Request) -> bool:
    """Return True if the request originates from localhost."""
    host = request.client.host if request.client else ""
    return host in {"127.0.0.1", "::1", "localhost"}


def session_token_valid(session: dict[str, Any], token: str | None) -> bool:
    """Constant-time check that ``token`` matches the session's access token."""
    if token is None:
        return False
    expected = session.get("access_token")
    if not isinstance(expected, str) or not expected:
        return False
    if not isinstance(token, str) or not token:
        return False
    return hmac.compare_digest(expected, token)


def resolve_session_token(request: Request, token: str | None) -> str | None:
    """Prefer an explicit token, otherwise fall back to the session cookie."""
    if token:
        return token
    return request.cookies.get("scrumtious_session_token")

"""Token validation and access control helpers.

Each session is protected by a per-session ``access_token`` (also set as an
httponly cookie). These helpers perform constant-time comparison and resolve the
token from either the query string or the cookie.
"""

import hmac
from typing import Any

from fastapi import Request

from app import config

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def resolve_client_host(request: Request) -> str:
    """Resolve the client's network identity, proxy-aware.

    ``X-Forwarded-For`` is client-controlled, so it is only honoured when
    ``TRUST_PROXY=1`` declares a trusted reverse proxy in front of the app.
    In that case the *last* entry is used — the hop appended by our own
    proxy — because any earlier entries can be forged by the client.
    """
    if config.TRUST_PROXY:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            hop = xff.split(",")[-1].strip()
            if hop:
                return hop
    return request.client.host if request.client else "unknown"


def is_local_request(request: Request) -> bool:
    """Return True if the request originates from localhost.

    Uses the proxy-aware client host: behind a reverse proxy on the same
    machine every connection arrives from 127.0.0.1, so without
    ``TRUST_PROXY=1`` this check would treat all traffic as local and
    silently disable the local-only gate on admin endpoints.
    """
    return resolve_client_host(request) in _LOOPBACK_HOSTS


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

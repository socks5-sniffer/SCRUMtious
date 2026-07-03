"""Simple in-process, per-client sliding-window rate limiter.

Guards the expensive ``POST /api/run`` endpoint. State is per-process; behind
multiple workers each process keeps its own window (see docs/architecture.md).

Client identity comes from :func:`app.security.auth.resolve_client_host`, so
``X-Forwarded-For`` is only trusted when ``TRUST_PROXY=1`` — otherwise anyone
could mint a fresh rate bucket per request by forging the header.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.config import RUN_RATE_LIMIT_PER_MINUTE
from app.security.auth import resolve_client_host

_WINDOW_SECONDS = 60

_run_rate_limit: dict[str, deque[float]] = defaultdict(deque)
_run_rate_limit_lock = threading.Lock()

# Once the table holds this many distinct clients, expired windows are pruned
# so a flood of spoofed identities cannot grow memory without bound.
_PRUNE_THRESHOLD = 1024


def _prune_expired_locked(now: float) -> None:
    """Drop clients whose most recent request is outside the window."""
    stale = [
        client_id
        for client_id, window in _run_rate_limit.items()
        if not window or (now - window[-1]) > _WINDOW_SECONDS
    ]
    for client_id in stale:
        del _run_rate_limit[client_id]


def consume_run_token(client_id: str) -> bool:
    """Record a request for ``client_id``; return False if over the limit."""
    now = time.time()
    with _run_rate_limit_lock:
        if len(_run_rate_limit) > _PRUNE_THRESHOLD:
            _prune_expired_locked(now)
        window = _run_rate_limit[client_id]
        while window and (now - window[0]) > _WINDOW_SECONDS:
            window.popleft()
        if len(window) >= RUN_RATE_LIMIT_PER_MINUTE:
            return False
        window.append(now)
        return True


def client_identifier(request: Request) -> str:
    """Client identity used as the rate-limit key (proxy-aware)."""
    return resolve_client_host(request)

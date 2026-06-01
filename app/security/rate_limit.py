"""Simple in-process, per-client sliding-window rate limiter.

Guards the expensive ``POST /api/run`` endpoint. State is per-process; behind
multiple workers each process keeps its own window (see docs/architecture.md).
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.config import RUN_RATE_LIMIT_PER_MINUTE

_run_rate_limit: dict[str, deque[float]] = defaultdict(deque)
_run_rate_limit_lock = threading.Lock()


def consume_run_token(client_id: str) -> bool:
    """Record a request for ``client_id``; return False if over the limit."""
    now = time.time()
    with _run_rate_limit_lock:
        window = _run_rate_limit[client_id]
        while window and (now - window[0]) > 60:
            window.popleft()
        if len(window) >= RUN_RATE_LIMIT_PER_MINUTE:
            return False
        window.append(now)
        return True


def client_identifier(request: Request) -> str:
    """Best-effort client identity, honouring a single X-Forwarded-For hop."""
    xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if xff:
        return xff
    return request.client.host if request.client else "unknown"

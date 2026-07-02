"""Tests for proxy-aware client identity and rate-limiter hygiene."""

import time
from types import SimpleNamespace

from app import config
from app.security import rate_limit
from app.security.auth import is_local_request, resolve_client_host


def _req(host="203.0.113.7", xff=None):
    headers = {}
    if xff is not None:
        headers["x-forwarded-for"] = xff
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def test_xff_ignored_by_default(monkeypatch):
    monkeypatch.setattr(config, "TRUST_PROXY", False)
    # A forged header must not mint a new identity when no proxy is declared.
    assert resolve_client_host(_req(xff="6.6.6.6")) == "203.0.113.7"


def test_xff_last_hop_wins_when_proxy_trusted(monkeypatch):
    monkeypatch.setattr(config, "TRUST_PROXY", True)
    # The client can forge earlier entries; only the proxy-appended last hop counts.
    assert (
        resolve_client_host(_req(host="127.0.0.1", xff="6.6.6.6, 198.51.100.9"))
        == "198.51.100.9"
    )


def test_xff_missing_falls_back_to_socket_peer(monkeypatch):
    monkeypatch.setattr(config, "TRUST_PROXY", True)
    assert resolve_client_host(_req(host="203.0.113.7")) == "203.0.113.7"


def test_is_local_request_sees_through_local_proxy(monkeypatch):
    monkeypatch.setattr(config, "TRUST_PROXY", True)
    # Behind a same-host proxy the socket peer is loopback but the client is remote.
    assert not is_local_request(_req(host="127.0.0.1", xff="198.51.100.9"))


def test_is_local_request_direct_loopback(monkeypatch):
    monkeypatch.setattr(config, "TRUST_PROXY", False)
    assert is_local_request(_req(host="127.0.0.1"))
    assert not is_local_request(_req(host="203.0.113.7"))


def test_rate_limiter_prunes_stale_clients(monkeypatch):
    monkeypatch.setattr(rate_limit, "_PRUNE_THRESHOLD", 4)
    rate_limit._run_rate_limit.clear()
    stale = time.time() - 120
    for i in range(10):
        rate_limit._run_rate_limit[f"spoof-{i}"].append(stale)

    assert rate_limit.consume_run_token("real-client")
    assert "real-client" in rate_limit._run_rate_limit
    # The flood of expired identities is evicted rather than kept forever.
    assert not any(k.startswith("spoof-") for k in rate_limit._run_rate_limit)

    rate_limit._run_rate_limit.clear()


def test_rate_limiter_still_enforces_limit():
    rate_limit._run_rate_limit.clear()
    for _ in range(rate_limit.RUN_RATE_LIMIT_PER_MINUTE):
        assert rate_limit.consume_run_token("busy-client")
    assert not rate_limit.consume_run_token("busy-client")
    rate_limit._run_rate_limit.clear()

"""Tests for compute.ingest.sec_health.

The probe is a thin requests wrapper, so the tests mock requests.get
and verify the state-machine output. Network is never hit.

The state ladder lives in the helper module's docstring:
    < 5s     → HEALTHY
    5-15s    → THROTTLED
    >= 15s   → DEGRADED
    non-200  → DEGRADED
    exception → DEGRADED
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from compute.ingest.sec_health import (
    SecApiHealth,
    assert_sec_api_usable,
    probe_sec_api,
)


def _mock_response(status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    return r


def test_probe_healthy_when_fast_200(monkeypatch):
    """< 5s + HTTP 200 → HEALTHY."""
    monkeypatch.setenv("EDGAR_USER_AGENT", "Tester tester@example.com")
    times = iter([0.0, 1.5])  # 1.5s elapsed
    with patch("compute.ingest.sec_health.time.perf_counter", side_effect=lambda: next(times)), \
         patch("compute.ingest.sec_health.requests.get", return_value=_mock_response(200)):
        result = probe_sec_api()
    assert result.state == SecApiHealth.HEALTHY
    assert result.latency_seconds == pytest.approx(1.5)
    assert result.http_status == 200
    assert result.error is None


def test_probe_throttled_when_5_to_15_seconds(monkeypatch):
    """5-15s + HTTP 200 → THROTTLED."""
    monkeypatch.setenv("EDGAR_USER_AGENT", "Tester tester@example.com")
    times = iter([0.0, 8.0])  # 8s elapsed
    with patch("compute.ingest.sec_health.time.perf_counter", side_effect=lambda: next(times)), \
         patch("compute.ingest.sec_health.requests.get", return_value=_mock_response(200)):
        result = probe_sec_api()
    assert result.state == SecApiHealth.THROTTLED
    assert result.latency_seconds == pytest.approx(8.0)


def test_probe_degraded_when_over_15_seconds(monkeypatch):
    """≥ 15s + HTTP 200 → DEGRADED (still reachable but unusable for full run)."""
    monkeypatch.setenv("EDGAR_USER_AGENT", "Tester tester@example.com")
    times = iter([0.0, 16.5])
    with patch("compute.ingest.sec_health.time.perf_counter", side_effect=lambda: next(times)), \
         patch("compute.ingest.sec_health.requests.get", return_value=_mock_response(200)):
        result = probe_sec_api()
    assert result.state == SecApiHealth.DEGRADED
    assert result.http_status == 200


def test_probe_degraded_on_non_200(monkeypatch):
    """403/429/500 → DEGRADED regardless of latency."""
    monkeypatch.setenv("EDGAR_USER_AGENT", "Tester tester@example.com")
    times = iter([0.0, 1.0])
    with patch("compute.ingest.sec_health.time.perf_counter", side_effect=lambda: next(times)), \
         patch("compute.ingest.sec_health.requests.get", return_value=_mock_response(429)):
        result = probe_sec_api()
    assert result.state == SecApiHealth.DEGRADED
    assert result.http_status == 429
    assert "HTTP 429" in (result.error or "")


def test_probe_degraded_on_network_exception(monkeypatch):
    """requests.Timeout / ConnectionError → DEGRADED."""
    monkeypatch.setenv("EDGAR_USER_AGENT", "Tester tester@example.com")
    with patch("compute.ingest.sec_health.requests.get",
               side_effect=requests.Timeout("timed out")):
        result = probe_sec_api()
    assert result.state == SecApiHealth.DEGRADED
    assert result.http_status is None
    assert "timed out" in (result.error or "")


def test_probe_degraded_when_user_agent_missing(monkeypatch):
    """No EDGAR_USER_AGENT → DEGRADED without even hitting the network.
    SEC EDGAR 403s on requests without a real UA; no point probing."""
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
    # Should NOT make a network call — assert by raising on requests.get.
    with patch("compute.ingest.sec_health.requests.get",
               side_effect=AssertionError("network should not be hit")):
        result = probe_sec_api()
    assert result.state == SecApiHealth.DEGRADED
    assert result.error == "EDGAR_USER_AGENT not set"


def test_assert_proceeds_on_healthy(monkeypatch):
    """assert_sec_api_usable returns normally on HEALTHY."""
    monkeypatch.setenv("EDGAR_USER_AGENT", "Tester tester@example.com")
    times = iter([0.0, 1.0])
    with patch("compute.ingest.sec_health.time.perf_counter", side_effect=lambda: next(times)), \
         patch("compute.ingest.sec_health.requests.get", return_value=_mock_response(200)):
        result = assert_sec_api_usable()
    assert result.state == SecApiHealth.HEALTHY


def test_assert_proceeds_on_throttled(monkeypatch):
    """THROTTLED logs a warning but doesn't abort — compute can still run,
    just slowly."""
    monkeypatch.setenv("EDGAR_USER_AGENT", "Tester tester@example.com")
    times = iter([0.0, 10.0])
    with patch("compute.ingest.sec_health.time.perf_counter", side_effect=lambda: next(times)), \
         patch("compute.ingest.sec_health.requests.get", return_value=_mock_response(200)):
        result = assert_sec_api_usable()
    assert result.state == SecApiHealth.THROTTLED


def test_assert_raises_on_degraded(monkeypatch):
    """DEGRADED raises RuntimeError; caller in compute.main catches it
    and returns 0 to exit the workflow non-zero."""
    monkeypatch.setenv("EDGAR_USER_AGENT", "Tester tester@example.com")
    times = iter([0.0, 20.0])
    with patch("compute.ingest.sec_health.time.perf_counter", side_effect=lambda: next(times)), \
         patch("compute.ingest.sec_health.requests.get", return_value=_mock_response(200)):
        with pytest.raises(RuntimeError, match="SEC API health"):
            assert_sec_api_usable()


def test_assert_skipped_via_env_var(monkeypatch):
    """QR_SKIP_SEC_HEALTH=1 bypasses the probe entirely. Useful for
    testing compute against cache-only data with no live SEC."""
    monkeypatch.setenv("QR_SKIP_SEC_HEALTH", "1")
    # Patch requests.get to assert no network call.
    with patch("compute.ingest.sec_health.requests.get",
               side_effect=AssertionError("network should not be hit")):
        result = assert_sec_api_usable()
    assert result.state == SecApiHealth.HEALTHY
    assert result.error == "skipped"

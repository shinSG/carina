"""Tests for the circuit breaker state machine."""

from __future__ import annotations

import time

from carina.health import CircuitBreaker
from carina.models import CircuitState


def test_opens_after_threshold():
    cb = CircuitBreaker(fail_threshold=3, reset_timeout_s=10)
    assert cb.allow()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow() is False


def test_half_open_then_closed_on_success():
    cb = CircuitBreaker(fail_threshold=1, reset_timeout_s=0.01)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    time.sleep(0.02)
    assert cb.allow() is True  # transitions to half-open
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_half_open_failure_reopens():
    cb = CircuitBreaker(fail_threshold=1, reset_timeout_s=0.01)
    cb.record_failure()
    time.sleep(0.02)
    assert cb.allow() is True
    cb.record_failure()  # fails the probe
    assert cb.state == CircuitState.OPEN

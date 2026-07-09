"""Circuit breaker and background health monitoring for providers."""

from __future__ import annotations

import asyncio
import time

from carina.adapters import build_adapter
from carina.models import CircuitState, HealthRecord, ProviderProfile
from carina.store import ConfigStore


class CircuitBreaker:
    """Per-provider circuit breaker (closed -> open -> half-open -> closed)."""

    def __init__(self, fail_threshold: int = 3, reset_timeout_s: float = 30.0) -> None:
        self.fail_threshold = fail_threshold
        self.reset_timeout_s = reset_timeout_s
        self.state = CircuitState.CLOSED
        self.fail_count = 0
        self._opened_at: float | None = None

    def allow(self) -> bool:
        """Whether a request may be attempted now."""
        if self.state == CircuitState.OPEN:
            if self._opened_at is not None and (
                time.monotonic() - self._opened_at >= self.reset_timeout_s
            ):
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def record_success(self) -> None:
        self.fail_count = 0
        self.state = CircuitState.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        self.fail_count += 1
        if self.state == CircuitState.HALF_OPEN or self.fail_count >= self.fail_threshold:
            self.state = CircuitState.OPEN
            self._opened_at = time.monotonic()


class HealthMonitor:
    """Tracks circuit breakers and health records; runs a background probe loop."""

    def __init__(
        self,
        store: ConfigStore,
        interval_s: float = 30.0,
        fail_threshold: int = 3,
        reset_timeout_s: float = 30.0,
    ) -> None:
        self._store = store
        self._interval_s = interval_s
        self._fail_threshold = fail_threshold
        self._reset_timeout_s = reset_timeout_s
        self._breakers: dict[str, CircuitBreaker] = {}
        self._records: dict[str, HealthRecord] = {}
        self._task: asyncio.Task[None] | None = None

    # --- breaker access ---------------------------------------------------

    def breaker(self, provider_id: str) -> CircuitBreaker:
        breaker = self._breakers.get(provider_id)
        if breaker is None:
            breaker = CircuitBreaker(self._fail_threshold, self._reset_timeout_s)
            self._breakers[provider_id] = breaker
        return breaker

    def allow(self, provider_id: str) -> bool:
        return self.breaker(provider_id).allow()

    def record_success(self, provider_id: str) -> None:
        self.breaker(provider_id).record_success()
        rec = self._records.setdefault(provider_id, HealthRecord(provider_id=provider_id))
        rec.healthy = True
        rec.fail_count = 0
        rec.state = self.breaker(provider_id).state
        rec.detail = "ok"

    def record_failure(self, provider_id: str, detail: str | None = None) -> None:
        breaker = self.breaker(provider_id)
        breaker.record_failure()
        rec = self._records.setdefault(provider_id, HealthRecord(provider_id=provider_id))
        rec.healthy = breaker.state != CircuitState.OPEN
        rec.fail_count = breaker.fail_count
        rec.state = breaker.state
        rec.detail = detail

    # --- reporting --------------------------------------------------------

    def records(self) -> list[HealthRecord]:
        out: list[HealthRecord] = []
        for provider in self._store.list_providers():
            rec = self._records.get(provider.id)
            breaker = self._breakers.get(provider.id)
            if rec is None:
                rec = HealthRecord(provider_id=provider.id)
            if breaker is not None:
                rec.state = breaker.state
            out.append(rec)
        return out

    # --- probing ----------------------------------------------------------

    async def probe(self, provider: ProviderProfile) -> None:
        adapter = build_adapter(provider)
        start = time.monotonic()
        try:
            ok, detail = await adapter.validate()
        except Exception as exc:  # noqa: BLE001 - adapters may raise arbitrary errors
            ok, detail = False, str(exc)
        latency_ms = (time.monotonic() - start) * 1000.0
        rec = self._records.setdefault(provider.id, HealthRecord(provider_id=provider.id))
        rec.last_check = time.time()
        rec.latency_ms = latency_ms
        if ok:
            self.record_success(provider.id)
        else:
            self.record_failure(provider.id, detail)

    async def _loop(self) -> None:
        while True:
            for provider in self._store.list_providers():
                if provider.enabled:
                    await self.probe(provider)
            await asyncio.sleep(self._interval_s)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

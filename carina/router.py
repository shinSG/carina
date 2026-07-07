"""Request routing with active-provider selection, failover, and breakers."""

from __future__ import annotations

from collections.abc import AsyncIterator

from carina.adapters import AdapterError, build_adapter
from carina.health import HealthMonitor
from carina.models import ChatRequest, ChatResponse, ProviderProfile
from carina.store import ConfigStore


class NoProviderAvailableError(RuntimeError):
    """Raised when no enabled, circuit-closed provider can serve the request."""


class Router:
    """Selects a provider for each request and fails over on errors."""

    def __init__(self, store: ConfigStore, monitor: HealthMonitor) -> None:
        self._store = store
        self._monitor = monitor

    def _candidates(self) -> list[ProviderProfile]:
        """Active provider first, then remaining enabled providers by priority."""
        providers = [p for p in self._store.list_providers() if p.enabled]
        active_id = self._store.active_id()
        providers.sort(key=lambda p: (p.id != active_id, p.priority, p.name))
        return providers

    def _allowed(self) -> list[ProviderProfile]:
        return [p for p in self._candidates() if self._monitor.allow(p.id)]

    async def forward(self, req: ChatRequest) -> ChatResponse:
        candidates = self._allowed()
        if not candidates:
            raise NoProviderAvailableError("no healthy provider available")
        last_error: Exception | None = None
        for provider in candidates:
            adapter = build_adapter(provider)
            try:
                resp = await adapter.forward(req)
            except AdapterError as exc:
                last_error = exc
                self._monitor.record_failure(provider.id, str(exc))
                continue
            self._monitor.record_success(provider.id)
            # Preserve the client's original model name in the response.
            resp.model = req.model or resp.model
            return resp
        raise NoProviderAvailableError(f"all providers failed; last error: {last_error}")

    async def stream(self, req: ChatRequest) -> tuple[ProviderProfile, AsyncIterator[str]]:
        """Return the chosen provider and a delta stream, failing over before first byte.

        Failover applies to connection/initial-status errors. Once streaming has
        started, an error is propagated (we cannot retry mid-stream safely).
        """
        candidates = self._allowed()
        if not candidates:
            raise NoProviderAvailableError("no healthy provider available")
        last_error: Exception | None = None
        for provider in candidates:
            adapter = build_adapter(provider)
            agen = adapter.stream(req)
            try:
                first = await agen.__anext__()
            except StopAsyncIteration:
                # Empty but successful stream.
                self._monitor.record_success(provider.id)
                return provider, _empty_stream()
            except AdapterError as exc:
                last_error = exc
                self._monitor.record_failure(provider.id, str(exc))
                continue
            self._monitor.record_success(provider.id)
            return provider, _prepend(first, agen)
        raise NoProviderAvailableError(f"all providers failed; last error: {last_error}")


async def _empty_stream() -> AsyncIterator[str]:
    return
    yield  # pragma: no cover - makes this an async generator


async def _prepend(first: str, rest: AsyncIterator[str]) -> AsyncIterator[str]:
    yield first
    async for item in rest:
        yield item

"""Request routing with active-provider selection, failover, and breakers."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

from carina.adapters import AdapterError, build_adapter
from carina.health import HealthMonitor
from carina.models import ChatRequest, ChatResponse, ProviderProfile
from carina.routing import MetricsStore, RankedProvider, RoutingPolicy
from carina.store import ConfigStore


class NoProviderAvailableError(RuntimeError):
    """Raised when no enabled, circuit-closed provider can serve the request."""


class Router:
    """Selects a provider for each request and fails over on errors."""

    def __init__(
        self,
        store: ConfigStore,
        monitor: HealthMonitor,
        metrics: MetricsStore | None = None,
    ) -> None:
        self._store = store
        self._monitor = monitor
        self.metrics = metrics or MetricsStore()
        self._policy = RoutingPolicy(self.metrics)

    def _ranked(self, req: ChatRequest) -> list[RankedProvider]:
        providers = self._store.list_providers()
        allowed_ids = {
            provider.id
            for provider in providers
            if provider.enabled and self._monitor.allow(provider.id)
        }
        return self._policy.evaluate(
            req,
            providers,
            self._store.active_id(),
            self._store.routing_config(),
            allowed_ids,
        )

    def _allowed(self, req: ChatRequest) -> list[ProviderProfile]:
        return [item.provider for item in self._ranked(req) if item.allowed]

    def preview(self, req: ChatRequest) -> dict:
        """Explain how the current policy would rank a request without forwarding it."""
        config = self._store.routing_config()
        ranked = self._ranked(req)
        return {
            "mode": config.mode,
            "selected_provider_id": next(
                (item.provider.id for item in ranked if item.allowed), None
            ),
            "candidates": [
                {
                    "provider_id": item.provider.id,
                    "provider_name": item.provider.name,
                    "allowed": item.allowed,
                    "score": item.score,
                    "matched_rule": item.matched_rule,
                    "reasons": item.reasons,
                }
                for item in ranked
            ],
        }

    async def forward(self, req: ChatRequest) -> ChatResponse:
        candidates = self._allowed(req)
        if not candidates:
            raise NoProviderAvailableError("no healthy provider available")
        last_error: Exception | None = None
        for provider in candidates:
            adapter = build_adapter(provider)
            start = time.monotonic()
            try:
                resp = await adapter.forward(req)
            except AdapterError as exc:
                last_error = exc
                self._monitor.record_failure(provider.id, str(exc))
                self.metrics.record_failure(provider.id)
                continue
            self._monitor.record_success(provider.id)
            latency_ms = (time.monotonic() - start) * 1000.0
            self.metrics.record_success(
                provider.id,
                latency_ms,
                alpha=self._store.routing_config().ewma_alpha,
                input_tokens=resp.usage.prompt_tokens,
                output_tokens=resp.usage.completion_tokens,
                estimated_cost=_estimated_cost(provider, resp),
            )
            return resp
        raise NoProviderAvailableError(f"all providers failed; last error: {last_error}")

    async def stream(self, req: ChatRequest) -> tuple[ProviderProfile, AsyncIterator[str]]:
        """Return the chosen provider and a delta stream, failing over before first byte.

        Failover applies to connection/initial-status errors. Once streaming has
        started, an error is propagated (we cannot retry mid-stream safely).
        """
        candidates = self._allowed(req)
        if not candidates:
            raise NoProviderAvailableError("no healthy provider available")
        last_error: Exception | None = None
        for provider in candidates:
            adapter = build_adapter(provider)
            agen = adapter.stream(req)
            start = time.monotonic()
            try:
                first = await agen.__anext__()
            except StopAsyncIteration:
                # Empty but successful stream.
                self._monitor.record_success(provider.id)
                elapsed_ms = (time.monotonic() - start) * 1000.0
                self.metrics.record_success(
                    provider.id,
                    elapsed_ms,
                    alpha=self._store.routing_config().ewma_alpha,
                    first_byte_ms=elapsed_ms,
                )
                return provider, _empty_stream()
            except AdapterError as exc:
                last_error = exc
                self._monitor.record_failure(provider.id, str(exc))
                self.metrics.record_failure(provider.id)
                continue
            first_byte_ms = (time.monotonic() - start) * 1000.0
            return provider, self._observe_stream(provider, first, agen, start, first_byte_ms)
        raise NoProviderAvailableError(f"all providers failed; last error: {last_error}")

    async def _observe_stream(
        self,
        provider: ProviderProfile,
        first: str,
        rest: AsyncIterator[str],
        start: float,
        first_byte_ms: float,
    ) -> AsyncIterator[str]:
        try:
            yield first
            async for item in rest:
                yield item
        except AdapterError as exc:
            self._monitor.record_failure(provider.id, str(exc))
            self.metrics.record_failure(provider.id)
            raise
        else:
            self._monitor.record_success(provider.id)
            self.metrics.record_success(
                provider.id,
                (time.monotonic() - start) * 1000.0,
                alpha=self._store.routing_config().ewma_alpha,
                first_byte_ms=first_byte_ms,
            )


async def _empty_stream() -> AsyncIterator[str]:
    return
    yield  # pragma: no cover - makes this an async generator


def _estimated_cost(provider: ProviderProfile, response: ChatResponse) -> float:
    input_cost = provider.input_cost_per_million or 0.0
    output_cost = provider.output_cost_per_million or 0.0
    return (
        response.usage.prompt_tokens * input_cost + response.usage.completion_tokens * output_cost
    ) / 1_000_000

"""Provider adapters: protocol-specific upstream clients.

Each adapter normalizes a :class:`ChatRequest` to its provider wire format,
calls the upstream, and returns a normalized :class:`ChatResponse` (or streams
normalized text deltas). Adding a provider = one new adapter + registry entry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable

from carina.models import ChatRequest, ChatResponse, ProviderProfile


class AdapterError(RuntimeError):
    """Raised when an upstream call fails. Carries an optional HTTP status."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ProviderAdapter(ABC):
    """Abstract base for all provider adapters."""

    protocol: str = ""

    def __init__(self, provider: ProviderProfile) -> None:
        self.provider = provider

    def _model(self, req: ChatRequest) -> str:
        return req.model or self.provider.default_model or "default"

    @abstractmethod
    async def forward(self, req: ChatRequest) -> ChatResponse:
        """Send a non-streaming request and return a normalized response."""

    @abstractmethod
    def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        """Yield normalized text deltas for a streaming request."""

    @abstractmethod
    async def validate(self) -> tuple[bool, str]:
        """Connectivity/credential check. Returns ``(ok, detail)``."""


_REGISTRY: dict[str, Callable[[ProviderProfile], ProviderAdapter]] = {}


def register(protocol: str, factory: Callable[[ProviderProfile], ProviderAdapter]) -> None:
    _REGISTRY[protocol] = factory


def build_adapter(provider: ProviderProfile) -> ProviderAdapter:
    """Instantiate the adapter registered for ``provider.protocol``."""
    try:
        factory = _REGISTRY[provider.protocol]
    except KeyError as exc:
        raise AdapterError(f"unknown protocol: {provider.protocol}") from exc
    return factory(provider)

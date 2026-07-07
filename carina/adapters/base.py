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


def is_retriable_error(exc: AdapterError) -> bool:
    """Whether an error is transient and model-level fallback should be tried."""
    code = exc.status_code
    if code is None:
        return True  # network/timeout — always retriable
    return code in (408, 429, 500, 502, 503, 504)


class ModelResolver:
    """Resolves client model name to a provider-specific model name.

    Resolution order:
      1. ``provider.model_map[client_model]`` if present
      2. ``provider.default_model`` if client model is None
      3. ``"default"`` as last resort
    """

    def __init__(self, provider: ProviderProfile) -> None:
        self._map = provider.model_map
        self._default = provider.default_model

    def resolve(self, client_model: str | None) -> str:
        if client_model:
            return self._map.get(client_model, client_model)
        return self._default or "default"


class ProviderAdapter(ABC):
    """Abstract base for all provider adapters."""

    protocol: str = ""

    def __init__(self, provider: ProviderProfile) -> None:
        self.provider = provider
        self.resolver = ModelResolver(provider)

    def _model(self, req: ChatRequest) -> str:
        return self.resolver.resolve(req.model)

    def _resolve_with_fallback(self, req: ChatRequest) -> list[str]:
        """Return ordered list of provider models to try: primary + fallbacks."""
        primary = self.resolver.resolve(req.model)
        fallbacks = [m for m in self.provider.fallback_models if m != primary]
        return [primary, *fallbacks]

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

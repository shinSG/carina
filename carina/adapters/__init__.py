"""Adapter package. Importing it registers all built-in adapters."""

from __future__ import annotations

from carina.adapters import anthropic, openai  # noqa: F401  (registration side effects)
from carina.adapters.base import (
    AdapterError,
    ProviderAdapter,
    build_adapter,
    register,
)

__all__ = [
    "AdapterError",
    "ProviderAdapter",
    "build_adapter",
    "register",
]

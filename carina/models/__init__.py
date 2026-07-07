"""Pydantic schemas for providers, config, and the internal chat model."""

from __future__ import annotations

import enum
import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

Protocol = Literal["openai", "anthropic", "passthrough"]


class ProviderProfile(BaseModel):
    """A single upstream model provider configuration."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    protocol: Protocol = "openai"
    base_url: str
    api_key: str = ""
    default_model: str | None = None
    extra_headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    priority: int = 100
    timeout_s: float = 60.0
    model_map: dict[str, str] = Field(default_factory=dict)
    """Client model name → provider model name. e.g. {"gpt-4o": "claude-sonnet-4-20250514"}."""
    fallback_models: list[str] = Field(default_factory=list)
    """Models to try in order when the primary model fails (retriable errors)."""

    def redacted(self) -> dict[str, Any]:
        """Return a dict safe for logging / API responses (no secret)."""
        data = self.model_dump()
        data["api_key"] = "***" if self.api_key else ""
        data["has_api_key"] = bool(self.api_key)
        return data


class ProviderCreate(BaseModel):
    """Payload to create a provider."""

    name: str
    protocol: Protocol = "openai"
    base_url: str
    api_key: str = ""
    default_model: str | None = None
    extra_headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    priority: int = 100
    timeout_s: float = 60.0
    model_map: dict[str, str] = Field(default_factory=dict)
    fallback_models: list[str] = Field(default_factory=list)


class ProviderUpdate(BaseModel):
    """Partial update payload for a provider. Unset fields are left unchanged."""

    name: str | None = None
    protocol: Protocol | None = None
    base_url: str | None = None
    api_key: str | None = None
    default_model: str | None = None
    extra_headers: dict[str, str] | None = None
    enabled: bool | None = None
    priority: int | None = None
    timeout_s: float | None = None
    model_map: dict[str, str] | None = None
    fallback_models: list[str] | None = None


class ProxyConfig(BaseModel):
    """Top-level persisted configuration."""

    version: int = 1
    active_id: str | None = None
    providers: list[ProviderProfile] = Field(default_factory=list)


# --- Internal normalized chat model (protocol-agnostic) -------------------


class Role(enum.StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    role: Role
    content: str


class ChatRequest(BaseModel):
    """Normalized inbound request used internally by adapters/translators."""

    model: str | None = None
    messages: list[ChatMessage]
    system: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    stream: bool = False


class ChatUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ChatResponse(BaseModel):
    """Normalized non-streaming response."""

    id: str = Field(default_factory=lambda: "carina-" + uuid.uuid4().hex[:16])
    model: str | None = None
    content: str = ""
    stop_reason: str | None = None
    usage: ChatUsage = Field(default_factory=ChatUsage)
    created: int = Field(default_factory=lambda: int(time.time()))


# --- Health -----------------------------------------------------------------


class CircuitState(enum.StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class HealthRecord(BaseModel):
    provider_id: str
    state: CircuitState = CircuitState.CLOSED
    healthy: bool = True
    last_check: float | None = None
    latency_ms: float | None = None
    fail_count: int = 0
    detail: str | None = None

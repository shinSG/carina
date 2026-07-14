"""Pydantic schemas for providers, config, and the internal chat model."""

from __future__ import annotations

import enum
import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

Protocol = Literal["openai", "anthropic", "passthrough"]
RoutingMode = Literal["manual", "rule", "adaptive"]


class RoutingRule(BaseModel):
    """A request matcher that narrows or prefers a group of providers."""

    name: str
    enabled: bool = True
    model_patterns: list[str] = Field(default_factory=list)
    stream: bool | None = None
    provider_ids: list[str] = Field(default_factory=list)
    require_tags: set[str] = Field(default_factory=set)
    prefer_tags: set[str] = Field(default_factory=set)
    strict: bool = False


class RoutingWeights(BaseModel):
    """Weights used by adaptive routing; values are normalized at scoring time."""

    success_rate: float = Field(default=0.30, ge=0)
    latency: float = Field(default=0.25, ge=0)
    priority: float = Field(default=0.20, ge=0)
    cost: float = Field(default=0.15, ge=0)
    preference: float = Field(default=0.10, ge=0)


class RoutingConfig(BaseModel):
    """Persisted smart-routing settings."""

    mode: RoutingMode = "manual"
    rules: list[RoutingRule] = Field(default_factory=list)
    weights: RoutingWeights = Field(default_factory=RoutingWeights)
    latency_target_ms: float = Field(default=2000.0, gt=0)
    ewma_alpha: float = Field(default=0.20, gt=0, le=1)
    active_provider_bonus: float = Field(default=0.05, ge=0)


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
    model_patterns: list[str] = Field(default_factory=list)
    capabilities: set[str] = Field(default_factory=set)
    tags: set[str] = Field(default_factory=set)
    context_window: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    input_cost_per_million: float | None = Field(default=None, ge=0)
    output_cost_per_million: float | None = Field(default=None, ge=0)

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
    model_patterns: list[str] = Field(default_factory=list)
    capabilities: set[str] = Field(default_factory=set)
    tags: set[str] = Field(default_factory=set)
    context_window: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    input_cost_per_million: float | None = Field(default=None, ge=0)
    output_cost_per_million: float | None = Field(default=None, ge=0)


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
    model_patterns: list[str] | None = None
    capabilities: set[str] | None = None
    tags: set[str] | None = None
    context_window: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    input_cost_per_million: float | None = Field(default=None, ge=0)
    output_cost_per_million: float | None = Field(default=None, ge=0)


class ProxyConfig(BaseModel):
    """Top-level persisted configuration."""

    version: int = 1
    active_id: str | None = None
    providers: list[ProviderProfile] = Field(default_factory=list)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)


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


class RoutingPreviewRequest(BaseModel):
    """Small request shape accepted by the routing preview endpoint."""

    model: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    max_tokens: int | None = None
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

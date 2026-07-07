"""Tests for model mapping and model-level fallback."""

from __future__ import annotations

import json

import httpx
import pytest

from carina.adapters.anthropic import AnthropicAdapter
from carina.adapters.base import AdapterError, ModelResolver, is_retriable_error
from carina.adapters.openai import OpenAIAdapter
from carina.models import ChatMessage, ChatRequest, ProviderProfile, Role

# ---------------------------------------------------------------------------
# ModelResolver
# ---------------------------------------------------------------------------


class TestModelResolver:
    def test_direct_passthrough(self):
        """No model_map, no default_model — client model passes through."""
        p = ProviderProfile(name="test", base_url="http://x", protocol="openai")
        r = ModelResolver(p)
        assert r.resolve("gpt-4o") == "gpt-4o"

    def test_map_applied(self):
        """model_map translates client model to provider model."""
        p = ProviderProfile(
            name="test",
            base_url="http://x",
            protocol="openai",
            model_map={"gpt-4o": "claude-sonnet-4-20250514"},
        )
        r = ModelResolver(p)
        assert r.resolve("gpt-4o") == "claude-sonnet-4-20250514"

    def test_map_unmapped_model_passthrough(self):
        """Models not in the map pass through unchanged."""
        p = ProviderProfile(
            name="test",
            base_url="http://x",
            protocol="openai",
            model_map={"gpt-4o": "claude-sonnet-4-20250514"},
        )
        r = ModelResolver(p)
        assert r.resolve("gpt-4o-mini") == "gpt-4o-mini"

    def test_none_model_uses_default(self):
        """When client sends no model, default_model is used."""
        p = ProviderProfile(
            name="test",
            base_url="http://x",
            protocol="openai",
            default_model="gpt-4o-mini",
        )
        r = ModelResolver(p)
        assert r.resolve(None) == "gpt-4o-mini"

    def test_none_model_fallback_to_default_string(self):
        """When no default_model either, literal 'default' is returned."""
        p = ProviderProfile(name="test", base_url="http://x", protocol="openai")
        r = ModelResolver(p)
        assert r.resolve(None) == "default"


# ---------------------------------------------------------------------------
# _resolve_with_fallback
# ---------------------------------------------------------------------------


class TestResolveWithFallback:
    def _make_adapter(self, **kwargs):
        p = ProviderProfile(name="test", base_url="http://x", protocol="openai", **kwargs)
        return OpenAIAdapter(p)

    def test_primary_only(self):
        a = self._make_adapter()
        assert a._resolve_with_fallback(ChatRequest(messages=[], model="gpt-4o")) == ["gpt-4o"]

    def test_primary_plus_fallbacks(self):
        a = self._make_adapter(fallback_models=["gpt-4o-mini", "gpt-3.5-turbo"])
        models = a._resolve_with_fallback(ChatRequest(messages=[], model="gpt-4o"))
        assert models == ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]

    def test_map_then_fallbacks(self):
        a = self._make_adapter(
            model_map={"gpt-4o": "claude-sonnet-4-20250514"},
            fallback_models=["claude-3-haiku-20240307"],
        )
        models = a._resolve_with_fallback(ChatRequest(messages=[], model="gpt-4o"))
        assert models == ["claude-sonnet-4-20250514", "claude-3-haiku-20240307"]

    def test_dedup_fallback_if_same_as_primary(self):
        a = self._make_adapter(fallback_models=["gpt-4o", "gpt-4o-mini"])
        models = a._resolve_with_fallback(ChatRequest(messages=[], model="gpt-4o"))
        assert models == ["gpt-4o", "gpt-4o-mini"]


# ---------------------------------------------------------------------------
# is_retriable_error
# ---------------------------------------------------------------------------


class TestIsRetriable:
    def test_none_status_is_retriable(self):
        assert is_retriable_error(AdapterError("timeout")) is True

    def test_429_is_retriable(self):
        assert is_retriable_error(AdapterError("rate limit", status_code=429)) is True

    def test_500_is_retriable(self):
        assert is_retriable_error(AdapterError("server error", status_code=500)) is True

    def test_400_is_not_retriable(self):
        assert is_retriable_error(AdapterError("bad request", status_code=400)) is False

    def test_401_is_not_retriable(self):
        assert is_retriable_error(AdapterError("unauthorized", status_code=401)) is False


# ---------------------------------------------------------------------------
# OpenAI adapter: model map + fallback
# ---------------------------------------------------------------------------


class TestOpenAIModelMapAndFallback:
    def _make_provider(self, **kwargs):
        return ProviderProfile(
            name="test", base_url="http://upstream", protocol="openai", api_key="sk-test", **kwargs
        )

    def _ok_handler(self, captured_models: list):
        """Return a handler that captures the model name and returns 200."""

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            captured_models.append(body.get("model"))
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-1",
                    "model": body.get("model"),
                    "choices": [
                        {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                },
            )

        return handler

    @pytest.mark.asyncio
    async def test_model_map_applied_in_forward(self, mock_upstream):
        captured: list[str] = []
        mock_upstream(self._ok_handler(captured))
        p = self._make_provider(model_map={"gpt-4o": "claude-sonnet-4-20250514"})
        adapter = OpenAIAdapter(p)
        req = ChatRequest(messages=[ChatMessage(role=Role.USER, content="hi")], model="gpt-4o")
        await adapter.forward(req)
        assert captured == ["claude-sonnet-4-20250514"]

    @pytest.mark.asyncio
    async def test_fallback_on_429(self, mock_upstream):
        """First model returns 429, second succeeds."""
        call_count = {"n": 0}
        captured_models: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            model = body.get("model")
            call_count["n"] += 1
            if model == "gpt-4o":
                return httpx.Response(429, json={"error": {"message": "rate limited"}})
            captured_models.append(model)
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-1",
                    "model": model,
                    "choices": [
                        {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                },
            )

        mock_upstream(handler)
        p = self._make_provider(fallback_models=["gpt-4o-mini"])
        adapter = OpenAIAdapter(p)
        req = ChatRequest(messages=[ChatMessage(role=Role.USER, content="hi")], model="gpt-4o")
        await adapter.forward(req)
        assert call_count["n"] == 2
        assert captured_models == ["gpt-4o-mini"]

    @pytest.mark.asyncio
    async def test_non_retriable_error_stops(self, mock_upstream):
        """401 should NOT trigger fallback — raise immediately."""
        call_count = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(401, json={"error": {"message": "unauthorized"}})

        mock_upstream(handler)
        p = self._make_provider(fallback_models=["gpt-4o-mini"])
        adapter = OpenAIAdapter(p)
        req = ChatRequest(messages=[ChatMessage(role=Role.USER, content="hi")], model="gpt-4o")
        with pytest.raises(AdapterError):
            await adapter.forward(req)
        assert call_count["n"] == 1  # only tried once


# ---------------------------------------------------------------------------
# Anthropic adapter: model map + fallback
# ---------------------------------------------------------------------------


class TestAnthropicModelMapAndFallback:
    def _make_provider(self, **kwargs):
        return ProviderProfile(
            name="test",
            base_url="http://upstream",
            protocol="anthropic",
            api_key="sk-ant-test",
            **kwargs,
        )

    def _ok_handler(self, captured_models: list):

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            captured_models.append(body.get("model"))
            return httpx.Response(
                200,
                json={
                    "id": "msg-1",
                    "type": "message",
                    "role": "assistant",
                    "model": body.get("model"),
                    "content": [{"type": "text", "text": "ok"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            )

        return handler

    @pytest.mark.asyncio
    async def test_model_map_applied_in_forward(self, mock_upstream):
        captured: list[str] = []
        mock_upstream(self._ok_handler(captured))
        p = self._make_provider(model_map={"gpt-4o": "claude-sonnet-4-20250514"})
        adapter = AnthropicAdapter(p)
        req = ChatRequest(messages=[ChatMessage(role=Role.USER, content="hi")], model="gpt-4o")
        await adapter.forward(req)
        assert captured == ["claude-sonnet-4-20250514"]

    @pytest.mark.asyncio
    async def test_fallback_on_500(self, mock_upstream):
        call_count = {"n": 0}
        captured_models: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            model = body.get("model")
            call_count["n"] += 1
            if model == "claude-sonnet-4-20250514":
                return httpx.Response(500, json={"error": {"message": "server error"}})
            captured_models.append(model)
            return httpx.Response(
                200,
                json={
                    "id": "msg-1",
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [{"type": "text", "text": "ok"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            )

        mock_upstream(handler)
        p = self._make_provider(fallback_models=["claude-3-haiku-20240307"])
        adapter = AnthropicAdapter(p)
        req = ChatRequest(
            messages=[ChatMessage(role=Role.USER, content="hi")], model="claude-sonnet-4-20250514"
        )
        await adapter.forward(req)
        assert call_count["n"] == 2
        assert captured_models == ["claude-3-haiku-20240307"]

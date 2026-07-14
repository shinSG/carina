"""Tests for request-aware and adaptive provider routing."""

from __future__ import annotations

from fastapi.testclient import TestClient

from carina.health import HealthMonitor
from carina.models import (
    ChatRequest,
    ProviderCreate,
    RoutingConfig,
    RoutingRule,
)
from carina.router import Router
from carina.server.app import create_app


def _request(model: str = "gpt-test", stream: bool = False) -> ChatRequest:
    return ChatRequest(model=model, messages=[], stream=stream)


def test_old_config_defaults_to_manual_mode(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"version":1,"active_id":null,"providers":[]}', encoding="utf-8")

    from carina.store import ConfigStore

    assert ConfigStore(path).routing_config().mode == "manual"


def test_manual_mode_preserves_active_first(store):
    active = store.add_provider(
        ProviderCreate(name="active", base_url="https://active/v1", priority=999)
    )
    store.add_provider(ProviderCreate(name="priority", base_url="https://other/v1", priority=1))
    router = Router(store, HealthMonitor(store))

    preview = router.preview(_request())

    assert preview["selected_provider_id"] == active.id
    assert preview["mode"] == "manual"


def test_rule_mode_filters_models_and_prefers_tags(store):
    general = store.add_provider(
        ProviderCreate(
            name="general",
            base_url="https://general/v1",
            priority=1,
            model_patterns=["gpt-*"],
            tags={"general"},
        )
    )
    reasoning = store.add_provider(
        ProviderCreate(
            name="reasoning",
            base_url="https://reasoning/v1",
            priority=100,
            model_patterns=["o3*"],
            tags={"reasoning"},
        )
    )
    store.set_routing_config(
        RoutingConfig(
            mode="rule",
            rules=[
                RoutingRule(
                    name="reasoning",
                    model_patterns=["o3*"],
                    prefer_tags={"reasoning"},
                )
            ],
        )
    )
    router = Router(store, HealthMonitor(store))

    preview = router.preview(_request("o3-mini"))

    assert preview["selected_provider_id"] == reasoning.id
    rejected = next(c for c in preview["candidates"] if c["provider_id"] == general.id)
    assert rejected["allowed"] is False
    assert "not supported" in rejected["reasons"][0]


def test_adaptive_mode_uses_runtime_success_rate(store):
    first = store.add_provider(
        ProviderCreate(name="first", base_url="https://first/v1", priority=10)
    )
    second = store.add_provider(
        ProviderCreate(name="second", base_url="https://second/v1", priority=10)
    )
    store.set_routing_config(
        RoutingConfig(
            mode="adaptive",
            active_provider_bonus=0,
            weights={
                "success_rate": 1,
                "latency": 0,
                "priority": 0,
                "cost": 0,
                "preference": 0,
            },
        )
    )
    router = Router(store, HealthMonitor(store))
    router.metrics.record_failure(first.id)
    router.metrics.record_success(second.id, 100, alpha=0.2)

    preview = router.preview(_request())

    assert preview["selected_provider_id"] == second.id
    assert preview["candidates"][0]["score"] > preview["candidates"][1]["score"]


def test_context_window_filter_is_explained(store):
    too_small = store.add_provider(
        ProviderCreate(name="small", base_url="https://small/v1", context_window=5)
    )
    suitable = store.add_provider(
        ProviderCreate(name="large", base_url="https://large/v1", context_window=100)
    )
    store.set_routing_config(RoutingConfig(mode="rule"))
    router = Router(store, HealthMonitor(store))

    preview = router.preview(ChatRequest(model="x", messages=[], system="a" * 40, max_tokens=5))

    assert preview["selected_provider_id"] == suitable.id
    rejected = next(c for c in preview["candidates"] if c["provider_id"] == too_small.id)
    assert "estimated context window exceeded" in rejected["reasons"]


def test_non_strict_rule_falls_back_without_rule_preferences(store):
    active = store.add_provider(
        ProviderCreate(name="active", base_url="https://active/v1", tags={"general"})
    )
    store.add_provider(ProviderCreate(name="other", base_url="https://other/v1", tags={"general"}))
    store.set_routing_config(
        RoutingConfig(
            mode="rule",
            rules=[
                RoutingRule(
                    name="missing-pool",
                    model_patterns=["gpt-*"],
                    require_tags={"missing"},
                    prefer_tags={"missing"},
                )
            ],
        )
    )
    router = Router(store, HealthMonitor(store))

    preview = router.preview(_request("gpt-test"))

    assert preview["selected_provider_id"] == active.id
    assert preview["candidates"][0]["matched_rule"] is None


def test_routing_control_api(store):
    provider = store.add_provider(ProviderCreate(name="p", base_url="https://p/v1", tags={"fast"}))
    client = TestClient(create_app(store=store, start_health=False))

    updated = client.put(
        "/api/routing/config",
        json={
            "mode": "rule",
            "rules": [
                {
                    "name": "streaming",
                    "stream": True,
                    "prefer_tags": ["fast"],
                }
            ],
        },
    )
    preview = client.post(
        "/api/routing/preview",
        json={"model": "any", "stream": True},
    )

    assert updated.status_code == 200
    assert client.get("/api/routing/config").json()["mode"] == "rule"
    assert preview.json()["selected_provider_id"] == provider.id
    assert preview.json()["candidates"][0]["matched_rule"] == "streaming"

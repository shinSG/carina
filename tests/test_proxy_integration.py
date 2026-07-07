"""Integration tests: proxy endpoints, streaming, failover, secret non-leak."""

from __future__ import annotations

import json
import logging

import httpx
from fastapi.testclient import TestClient

from carina.models import ProviderCreate
from carina.server.app import create_app


def _openai_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/chat/completions"):
        body = json.loads(request.content)
        if body.get("stream"):
            text = (
                'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
                "data: [DONE]\n\n"
            )
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})
        return httpx.Response(
            200,
            json={
                "id": "up-1",
                "model": "gpt-test",
                "choices": [
                    {"message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )
    return httpx.Response(200, json={"data": []})  # /models probe


def _make_client(store, monkeypatch, handler=_openai_handler):
    transport = httpx.MockTransport(handler)
    real_init = httpx.AsyncClient.__init__

    def init(self, *args, **kwargs):
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", init)
    app = create_app(store=store, start_health=False)
    return TestClient(app)


def test_openai_passthrough(store, monkeypatch):
    store.add_provider(
        ProviderCreate(name="p", protocol="openai", base_url="https://up/v1", api_key="sk-secret")
    )
    client = _make_client(store, monkeypatch)
    r = client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "Hello"


def test_anthropic_in_openai_provider_out(store, monkeypatch):
    store.add_provider(
        ProviderCreate(name="p", protocol="openai", base_url="https://up/v1", api_key="sk")
    )
    client = _make_client(store, monkeypatch)
    r = client.post(
        "/v1/messages", json={"messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "message"
    assert body["content"][0]["text"] == "Hello"


def test_streaming(store, monkeypatch):
    store.add_provider(
        ProviderCreate(name="p", protocol="openai", base_url="https://up/v1", api_key="sk")
    )
    client = _make_client(store, monkeypatch)
    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
    ) as r:
        text = "".join(chunk for chunk in r.iter_text())
    assert "Hel" in text and "lo" in text
    assert "[DONE]" in text


def test_control_api_crud_and_activate(store, monkeypatch):
    client = _make_client(store, monkeypatch)
    created = client.post(
        "/api/providers",
        json={"name": "a", "protocol": "openai", "base_url": "https://up/v1", "api_key": "sk"},
    ).json()
    pid = created["id"]
    assert created["api_key"] == "***"
    client.post(
        "/api/providers",
        json={"name": "b", "protocol": "openai", "base_url": "https://up/v1"},
    )
    act = client.post(f"/api/providers/{pid}/activate")
    assert act.json()["active_id"] == pid
    listing = client.get("/api/providers").json()
    assert len(listing["providers"]) == 2
    client.delete(f"/api/providers/{pid}")
    assert len(client.get("/api/providers").json()["providers"]) == 1


def test_failover_to_backup(store, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if request.url.path.endswith("/chat/completions"):
            if host == "bad":
                return httpx.Response(500, json={"error": "boom"})
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "from-good"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {},
                },
            )
        return httpx.Response(200, json={"data": []})

    primary = store.add_provider(
        ProviderCreate(name="bad", protocol="openai", base_url="https://bad/v1", priority=1)
    )
    store.add_provider(
        ProviderCreate(name="good", protocol="openai", base_url="https://good/v1", priority=2)
    )
    store.set_active(primary.id)
    client = _make_client(store, monkeypatch, handler=handler)
    r = client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "from-good"


def test_no_provider_returns_503(store, monkeypatch):
    client = _make_client(store, monkeypatch)
    r = client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 503


def test_api_key_never_logged(store, monkeypatch, caplog):
    store.add_provider(
        ProviderCreate(name="p", protocol="openai", base_url="https://up/v1", api_key="sk-LEAKME")
    )
    client = _make_client(store, monkeypatch)
    with caplog.at_level(logging.DEBUG):
        r = client.post(
            "/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]}
        )
    assert r.status_code == 200
    assert "sk-LEAKME" not in caplog.text
    # and not in control API responses
    assert "sk-LEAKME" not in client.get("/api/providers").text

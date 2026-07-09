"""Shared test fixtures."""

from __future__ import annotations

import httpx
import pytest

from carina.store import ConfigStore


@pytest.fixture
def store(tmp_path):
    return ConfigStore(path=tmp_path / "config.json")


class MockProvider:
    """A configurable upstream provider backed by httpx.MockTransport.

    Patches httpx.AsyncClient so adapter code calls this mock instead of network.
    """

    def __init__(self, handler):
        self.handler = handler

    def patch(self, monkeypatch):
        transport = httpx.MockTransport(self.handler)
        real_init = httpx.AsyncClient.__init__

        def init(self, *args, **kwargs):
            kwargs["transport"] = transport
            real_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", init)


@pytest.fixture
def mock_upstream(monkeypatch):
    def install(handler):
        MockProvider(handler).patch(monkeypatch)

    return install

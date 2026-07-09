"""Anthropic Messages provider adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from carina import translate
from carina.adapters.base import AdapterError, ProviderAdapter, register
from carina.models import ChatRequest, ChatResponse, ProviderProfile

_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAdapter(ProviderAdapter):
    protocol = "anthropic"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": _ANTHROPIC_VERSION,
        }
        if self.provider.api_key:
            headers["x-api-key"] = self.provider.api_key
        headers.update(self.provider.extra_headers)
        return headers

    def _url(self) -> str:
        return self.provider.base_url.rstrip("/") + "/messages"

    async def forward(self, req: ChatRequest) -> ChatResponse:
        body = translate.internal_to_anthropic(req, self._model(req))
        body["stream"] = False
        try:
            async with httpx.AsyncClient(timeout=self.provider.timeout_s) as client:
                resp = await client.post(self._url(), json=body, headers=self._headers())
        except httpx.HTTPError as exc:
            raise AdapterError(f"upstream request failed: {exc}") from exc
        if resp.status_code >= 400:
            raise AdapterError(
                f"upstream returned {resp.status_code}", status_code=resp.status_code
            )
        return translate.anthropic_response_to_internal(resp.json())

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        body = translate.internal_to_anthropic(req, self._model(req))
        body["stream"] = True
        try:
            async with httpx.AsyncClient(timeout=self.provider.timeout_s) as client:
                async with client.stream(
                    "POST", self._url(), json=body, headers=self._headers()
                ) as resp:
                    if resp.status_code >= 400:
                        await resp.aread()
                        raise AdapterError(
                            f"upstream returned {resp.status_code}",
                            status_code=resp.status_code,
                        )
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        delta = translate.parse_anthropic_sse_data(line[len("data:") :])
                        if delta:
                            yield delta
        except httpx.HTTPError as exc:
            raise AdapterError(f"upstream stream failed: {exc}") from exc

    async def validate(self) -> tuple[bool, str]:
        # Anthropic has no cheap unauthenticated probe; do a minimal messages call.
        body = {
            "model": self.provider.default_model or "claude-3-haiku-20240307",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}],
        }
        try:
            async with httpx.AsyncClient(timeout=min(self.provider.timeout_s, 10.0)) as client:
                resp = await client.post(self._url(), json=body, headers=self._headers())
        except httpx.HTTPError as exc:
            return False, f"connection failed: {exc}"
        # 200 (ok) or 400 (bad model but reachable+authed) both indicate connectivity.
        if resp.status_code < 400 or resp.status_code == 400:
            return True, "ok"
        return False, f"status {resp.status_code}"


def _factory(provider: ProviderProfile) -> AnthropicAdapter:
    return AnthropicAdapter(provider)


register("anthropic", _factory)

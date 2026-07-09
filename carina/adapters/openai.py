"""OpenAI Chat Completions provider adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from carina import translate
from carina.adapters.base import AdapterError, ProviderAdapter, register
from carina.models import ChatRequest, ChatResponse, ProviderProfile


class OpenAIAdapter(ProviderAdapter):
    protocol = "openai"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.provider.api_key:
            headers["Authorization"] = f"Bearer {self.provider.api_key}"
        headers.update(self.provider.extra_headers)
        return headers

    def _url(self) -> str:
        return self.provider.base_url.rstrip("/") + "/chat/completions"

    async def forward(self, req: ChatRequest) -> ChatResponse:
        body = translate.internal_to_openai(req, self._model(req))
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
        return translate.openai_response_to_internal(resp.json())

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        body = translate.internal_to_openai(req, self._model(req))
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
                        delta = translate.parse_openai_sse_line(line)
                        if delta:
                            yield delta
        except httpx.HTTPError as exc:
            raise AdapterError(f"upstream stream failed: {exc}") from exc

    async def validate(self) -> tuple[bool, str]:
        url = self.provider.base_url.rstrip("/") + "/models"
        try:
            async with httpx.AsyncClient(timeout=min(self.provider.timeout_s, 10.0)) as client:
                resp = await client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            return False, f"connection failed: {exc}"
        if resp.status_code < 400:
            return True, "ok"
        return False, f"status {resp.status_code}"


def _factory(provider: ProviderProfile) -> OpenAIAdapter:
    return OpenAIAdapter(provider)


register("openai", _factory)

"""OpenAI Chat Completions provider adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from carina import translate
from carina.adapters.base import AdapterError, ProviderAdapter, is_retriable_error, register
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
        models = self._resolve_with_fallback(req)
        last_exc: AdapterError | None = None
        for model in models:
            body = translate.internal_to_openai(req, model)
            body["stream"] = False
            try:
                async with httpx.AsyncClient(timeout=self.provider.timeout_s) as client:
                    resp = await client.post(self._url(), json=body, headers=self._headers())
            except httpx.HTTPError as exc:
                last_exc = AdapterError(f"upstream request failed: {exc}")
                continue
            if resp.status_code >= 400:
                last_exc = AdapterError(
                    f"upstream returned {resp.status_code}", status_code=resp.status_code
                )
                if is_retriable_error(last_exc) and model != models[-1]:
                    continue
                raise last_exc
            return translate.openai_response_to_internal(resp.json())
        raise last_exc or AdapterError("no models to try")

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        models = self._resolve_with_fallback(req)
        last_exc: AdapterError | None = None
        for model in models:
            body = translate.internal_to_openai(req, model)
            body["stream"] = True
            try:
                async with httpx.AsyncClient(timeout=self.provider.timeout_s) as client:
                    async with client.stream(
                        "POST", self._url(), json=body, headers=self._headers()
                    ) as resp:
                        if resp.status_code >= 400:
                            await resp.aread()
                            last_exc = AdapterError(
                                f"upstream returned {resp.status_code}",
                                status_code=resp.status_code,
                            )
                            if is_retriable_error(last_exc) and model != models[-1]:
                                break  # try next model
                            raise last_exc
                        async for line in resp.aiter_lines():
                            delta = translate.parse_openai_sse_line(line)
                            if delta:
                                yield delta
                        return  # success, done
            except httpx.HTTPError as exc:
                last_exc = AdapterError(f"upstream stream failed: {exc}")
                continue
        raise last_exc or AdapterError("no models to try")

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

"""Client-facing proxy endpoints (OpenAI + Anthropic) with streaming support."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from carina import translate
from carina.models import ChatRequest
from carina.router import NoProviderAvailableError
from carina.server import get_state

router = APIRouter()


async def _read_json(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def _error(status: int, message: str, kind: str = "openai") -> JSONResponse:
    if kind == "anthropic":
        payload = {"type": "error", "error": {"type": "api_error", "message": message}}
    else:
        payload = {"error": {"message": message, "type": "proxy_error"}}
    return JSONResponse(status_code=status, content=payload)


@router.post("/v1/chat/completions")
async def openai_chat_completions(request: Request, state=Depends(get_state)):
    body = await _read_json(request)
    req: ChatRequest = translate.openai_to_internal(body)

    if req.stream:
        try:
            provider, deltas = await state.router.stream(req)
        except NoProviderAvailableError as exc:
            return _error(503, str(exc), kind="openai")

        async def gen():
            resp_id = "carina-" + provider.id
            yield translate.openai_stream_prefix(req.model, resp_id)
            async for d in deltas:
                if d:
                    yield translate.openai_stream_delta(d, req.model, resp_id)
            yield translate.openai_stream_suffix(req.model, resp_id)

        return StreamingResponse(gen(), media_type="text/event-stream")

    try:
        resp = await state.router.forward(req)
    except NoProviderAvailableError as exc:
        return _error(503, str(exc), kind="openai")
    return JSONResponse(translate.internal_to_openai_response(resp))


@router.post("/v1/messages")
async def anthropic_messages(request: Request, state=Depends(get_state)):
    body = await _read_json(request)
    req: ChatRequest = translate.anthropic_to_internal(body)

    if req.stream:
        try:
            provider, deltas = await state.router.stream(req)
        except NoProviderAvailableError as exc:
            return _error(503, str(exc), kind="anthropic")

        async def gen():
            resp_id = "carina-" + provider.id
            yield translate.anthropic_stream_prefix(req.model, resp_id)
            async for d in deltas:
                if d:
                    yield translate.anthropic_stream_delta(d)
            yield translate.anthropic_stream_suffix()

        return StreamingResponse(gen(), media_type="text/event-stream")

    try:
        resp = await state.router.forward(req)
    except NoProviderAvailableError as exc:
        return _error(503, str(exc), kind="anthropic")
    return JSONResponse(translate.internal_to_anthropic_response(resp))

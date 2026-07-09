"""Translation between client/provider wire formats and the internal model.

Supports OpenAI Chat Completions and Anthropic Messages, in both the inbound
direction (client request -> :class:`ChatRequest`) and outbound direction
(:class:`ChatResponse` -> client wire format), including SSE streaming chunks.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterable
from typing import Any

from carina.models import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatUsage,
    Role,
)

# --- inbound: client wire format -> internal ChatRequest --------------------


def _coerce_content(content: Any) -> str:
    """Flatten OpenAI/Anthropic content (str or list of blocks) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") in (None, "text"):
                    parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return "".join(parts)
    return "" if content is None else str(content)


def openai_to_internal(body: dict[str, Any]) -> ChatRequest:
    """Parse an OpenAI Chat Completions request body."""
    messages: list[ChatMessage] = []
    system: str | None = None
    for msg in body.get("messages", []):
        role = msg.get("role", "user")
        text = _coerce_content(msg.get("content"))
        if role == "system":
            system = text if system is None else f"{system}\n{text}"
            continue
        if role not in (Role.USER.value, Role.ASSISTANT.value):
            role = Role.USER.value
        messages.append(ChatMessage(role=Role(role), content=text))
    return ChatRequest(
        model=body.get("model"),
        messages=messages,
        system=system,
        max_tokens=body.get("max_tokens"),
        temperature=body.get("temperature"),
        stream=bool(body.get("stream", False)),
    )


def anthropic_to_internal(body: dict[str, Any]) -> ChatRequest:
    """Parse an Anthropic Messages request body."""
    messages: list[ChatMessage] = []
    for msg in body.get("messages", []):
        role = msg.get("role", "user")
        if role not in (Role.USER.value, Role.ASSISTANT.value):
            role = Role.USER.value
        messages.append(ChatMessage(role=Role(role), content=_coerce_content(msg.get("content"))))
    system = body.get("system")
    if isinstance(system, list):
        system = _coerce_content(system)
    return ChatRequest(
        model=body.get("model"),
        messages=messages,
        system=system,
        max_tokens=body.get("max_tokens"),
        temperature=body.get("temperature"),
        stream=bool(body.get("stream", False)),
    )


# --- outbound: internal ChatRequest -> provider wire body -------------------


def internal_to_openai(req: ChatRequest, model: str) -> dict[str, Any]:
    """Build an OpenAI Chat Completions request body."""
    messages: list[dict[str, str]] = []
    if req.system:
        messages.append({"role": "system", "content": req.system})
    for m in req.messages:
        messages.append({"role": m.role.value, "content": m.content})
    body: dict[str, Any] = {"model": model, "messages": messages, "stream": req.stream}
    if req.max_tokens is not None:
        body["max_tokens"] = req.max_tokens
    if req.temperature is not None:
        body["temperature"] = req.temperature
    return body


def internal_to_anthropic(req: ChatRequest, model: str) -> dict[str, Any]:
    """Build an Anthropic Messages request body."""
    messages = [{"role": m.role.value, "content": m.content} for m in req.messages]
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        # Anthropic requires max_tokens.
        "max_tokens": req.max_tokens or 1024,
        "stream": req.stream,
    }
    if req.system:
        body["system"] = req.system
    if req.temperature is not None:
        body["temperature"] = req.temperature
    return body


# --- provider response -> internal ChatResponse -----------------------------


def openai_response_to_internal(body: dict[str, Any]) -> ChatResponse:
    choices = body.get("choices") or [{}]
    message = choices[0].get("message", {}) if choices else {}
    usage = body.get("usage", {}) or {}
    return ChatResponse(
        id=body.get("id", "carina-" + uuid.uuid4().hex[:16]),
        model=body.get("model"),
        content=_coerce_content(message.get("content")),
        stop_reason=choices[0].get("finish_reason") if choices else None,
        usage=ChatUsage(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        ),
    )


def anthropic_response_to_internal(body: dict[str, Any]) -> ChatResponse:
    usage = body.get("usage", {}) or {}
    return ChatResponse(
        id=body.get("id", "carina-" + uuid.uuid4().hex[:16]),
        model=body.get("model"),
        content=_coerce_content(body.get("content")),
        stop_reason=body.get("stop_reason"),
        usage=ChatUsage(
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
        ),
    )


# --- internal ChatResponse -> client wire format ----------------------------


def internal_to_openai_response(resp: ChatResponse) -> dict[str, Any]:
    return {
        "id": resp.id,
        "object": "chat.completion",
        "created": resp.created,
        "model": resp.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": resp.content},
                "finish_reason": resp.stop_reason or "stop",
            }
        ],
        "usage": {
            "prompt_tokens": resp.usage.prompt_tokens,
            "completion_tokens": resp.usage.completion_tokens,
            "total_tokens": resp.usage.prompt_tokens + resp.usage.completion_tokens,
        },
    }


def internal_to_anthropic_response(resp: ChatResponse) -> dict[str, Any]:
    return {
        "id": resp.id,
        "type": "message",
        "role": "assistant",
        "model": resp.model,
        "content": [{"type": "text", "text": resp.content}],
        "stop_reason": resp.stop_reason or "end_turn",
        "usage": {
            "input_tokens": resp.usage.prompt_tokens,
            "output_tokens": resp.usage.completion_tokens,
        },
    }


# --- streaming: normalized text deltas -> client SSE ------------------------

# OpenAI SSE: granular helpers so routes can stream incrementally.


def _openai_base(model: str | None, resp_id: str) -> dict[str, Any]:
    return {
        "id": resp_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
    }


def openai_stream_prefix(model: str | None, resp_id: str) -> str:
    chunk = {
        **_openai_base(model, resp_id),
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }
    return f"data: {json.dumps(chunk)}\n\n"


def openai_stream_delta(text: str, model: str | None, resp_id: str) -> str:
    chunk = {
        **_openai_base(model, resp_id),
        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
    }
    return f"data: {json.dumps(chunk)}\n\n"


def openai_stream_suffix(model: str | None, resp_id: str) -> str:
    final = {
        **_openai_base(model, resp_id),
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    return f"data: {json.dumps(final)}\n\ndata: [DONE]\n\n"


def openai_stream_events(deltas: Iterable[str], model: str | None, resp_id: str) -> Iterable[str]:
    """Yield OpenAI-style SSE ``data:`` lines for a sequence of text deltas."""
    yield openai_stream_prefix(model, resp_id)
    for text in deltas:
        if text:
            yield openai_stream_delta(text, model, resp_id)
    yield openai_stream_suffix(model, resp_id)


# Anthropic SSE: granular helpers.


def _anthropic_event(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def anthropic_stream_prefix(model: str | None, resp_id: str) -> str:
    start = _anthropic_event(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": resp_id,
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [],
                "stop_reason": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        },
    )
    block = _anthropic_event(
        "content_block_start",
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    )
    return start + block


def anthropic_stream_delta(text: str) -> str:
    return _anthropic_event(
        "content_block_delta",
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
    )


def anthropic_stream_suffix() -> str:
    return (
        _anthropic_event("content_block_stop", {"type": "content_block_stop", "index": 0})
        + _anthropic_event(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": 0},
            },
        )
        + _anthropic_event("message_stop", {"type": "message_stop"})
    )


def anthropic_stream_events(
    deltas: Iterable[str], model: str | None, resp_id: str
) -> Iterable[str]:
    """Yield Anthropic-style SSE events for a sequence of text deltas."""
    yield anthropic_stream_prefix(model, resp_id)
    for text in deltas:
        if text:
            yield anthropic_stream_delta(text)
    yield anthropic_stream_suffix()


# --- parsing upstream SSE chunks into normalized text deltas ----------------


def parse_openai_sse_line(line: str) -> str | None:
    """Extract the text delta from one upstream OpenAI SSE ``data:`` line."""
    line = line.strip()
    if not line.startswith("data:"):
        return None
    data = line[len("data:") :].strip()
    if not data or data == "[DONE]":
        return None
    try:
        obj = json.loads(data)
    except json.JSONDecodeError:
        return None
    choices = obj.get("choices") or []
    if not choices:
        return None
    return choices[0].get("delta", {}).get("content")


def parse_anthropic_sse_data(data: str) -> str | None:
    """Extract the text delta from one upstream Anthropic SSE ``data:`` payload."""
    data = data.strip()
    if not data:
        return None
    try:
        obj = json.loads(data)
    except json.JSONDecodeError:
        return None
    if obj.get("type") == "content_block_delta":
        return obj.get("delta", {}).get("text")
    return None

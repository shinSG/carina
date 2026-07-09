"""Tests for format translation in both directions, incl. SSE chunks."""

from __future__ import annotations

from carina import translate
from carina.models import ChatMessage, ChatRequest, ChatResponse, ChatUsage, Role


def test_openai_inbound_extracts_system_and_messages():
    body = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hi"},
        ],
        "stream": True,
    }
    req = translate.openai_to_internal(body)
    assert req.system == "be brief"
    assert req.stream is True
    assert [m.content for m in req.messages] == ["hi"]


def test_anthropic_inbound_block_content():
    body = {
        "model": "claude",
        "system": "sys",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
        "max_tokens": 50,
    }
    req = translate.anthropic_to_internal(body)
    assert req.system == "sys"
    assert req.max_tokens == 50
    assert req.messages[0].content == "hello"


def test_internal_to_anthropic_requires_max_tokens():
    req = ChatRequest(messages=[ChatMessage(role=Role.USER, content="hi")])
    body = translate.internal_to_anthropic(req, "claude")
    assert body["max_tokens"] == 1024  # default injected


def test_cross_protocol_openai_in_anthropic_out():
    # client sends OpenAI; provider speaks Anthropic
    req = translate.openai_to_internal(
        {"messages": [{"role": "user", "content": "ping"}], "model": "x"}
    )
    body = translate.internal_to_anthropic(req, "claude-3")
    assert body["model"] == "claude-3"
    assert body["messages"][0] == {"role": "user", "content": "ping"}


def test_response_mapping_openai_and_anthropic():
    resp = ChatResponse(
        model="m", content="hello", stop_reason="stop", usage=ChatUsage(prompt_tokens=3, completion_tokens=2)
    )
    oai = translate.internal_to_openai_response(resp)
    assert oai["choices"][0]["message"]["content"] == "hello"
    assert oai["usage"]["total_tokens"] == 5
    ant = translate.internal_to_anthropic_response(resp)
    assert ant["content"][0]["text"] == "hello"
    assert ant["usage"]["output_tokens"] == 2


def test_parse_upstream_sse():
    line = 'data: {"choices":[{"delta":{"content":"ab"}}]}'
    assert translate.parse_openai_sse_line(line) == "ab"
    assert translate.parse_openai_sse_line("data: [DONE]") is None
    ant = '{"type":"content_block_delta","delta":{"type":"text_delta","text":"cd"}}'
    assert translate.parse_anthropic_sse_data(ant) == "cd"


def test_stream_event_framing_openai():
    events = list(translate.openai_stream_events(["a", "b"], "m", "id1"))
    assert "[DONE]" in events[-1]
    assert any('"content": "a"' in e for e in events)


def test_stream_event_framing_anthropic():
    events = list(translate.anthropic_stream_events(["x"], "m", "id1"))
    assert "message_start" in events[0]
    assert "message_stop" in events[-1]

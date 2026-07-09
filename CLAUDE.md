# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

carina is a local model-service proxy that sits between AI client apps and upstream AI providers. It provides a single endpoint that can forward requests to multiple providers with protocol translation, health checking, and automatic failover.

## Commands

```bash
# Install (first time)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run the server
carina  # or: python -m carina

# Tests
pytest                    # all tests
pytest tests/test_store.py  # single file
pytest -k test_add         # by name

# Lint
ruff check
ruff format
```

## Architecture

The app is a **FastAPI** server serving both the proxy API and a static web UI. All state is in-memory, persisted to `~/.config/carina/config.json` (atomic writes with 0o600 permissions).

### Request flow

```
Client → proxy_routes.py → translate.py (to internal) → router.py (select provider) → adapters/ (to provider format) → upstream
```

Two client-facing endpoints accept either format:
- `POST /v1/chat/completions` (OpenAI format)
- `POST /v1/messages` (Anthropic format)

Both are normalized to an internal `ChatRequest` model, then re-serialized to whatever format the selected provider expects. This means a client can send OpenAI format to an Anthropic backend and vice versa.

### Key modules

- **`models/__init__.py`** — All Pydantic schemas: `ProviderProfile`, `ChatRequest`, `ChatResponse`, `HealthRecord`, circuit breaker states. `ChatRequest`/`ChatResponse` are the protocol-agnostic internal types.
- **`translate.py`** — Bidirectional conversion between client wire formats (OpenAI/Anthropic) and internal models, plus SSE streaming helpers. Stateless functions only.
- **`router.py`** — Selects which provider to use. Active provider is tried first, then remaining enabled providers sorted by `priority` value (lower = preferred). Implements failover: catches `AdapterError` and moves to next candidate.
- **`adapters/`** — Protocol-specific HTTP clients. Each adapter implements `forward()`, `stream()`, and `validate()`. Registered via `register()` in `__init__.py`. Currently: `openai.py` and `anthropic.py`.
- **`health.py`** — `HealthMonitor` runs background probes on all enabled providers. `CircuitBreaker` tracks per-provider state: `CLOSED` → `OPEN` (after 3 failures) → `HALF_OPEN` (after 30s) → back to `CLOSED` on success.
- **`store/__init__.py`** — Thread-safe JSON file persistence. All reads/writes go through `ConfigStore` with an `RLock`. Corrupt files are backed up as `.corrupt` and replaced with a fresh config.
- **`server/app.py`** — FastAPI factory. Mounts control routes (`/api/*`), proxy routes (`/v1/*`), and static files from `carina/web/`.
- **`web/`** — Static frontend (vanilla HTML+JS, no build step). Served by FastAPI's `StaticFiles` mount at `/`.

### Provider selection logic

1. Filter to enabled providers whose circuit breaker is not OPEN
2. Sort: active provider first, then by `priority` ascending, then by name
3. Try each in order; on `AdapterError`, record failure and continue to next
4. If all fail, raise `NoProviderAvailableError` → 503

### Model name resolution

In `adapters/base.py`: `req.model or provider.default_model or "default"` — client's requested model takes priority, falls back to provider config, then to literal string `"default"`.

### Adding a new adapter

Create `carina/adapters/your_protocol.py`, subclass `ProviderAdapter`, implement `forward()`, `stream()`, and `validate()`, then call `register("your_protocol", factory)`. Import it in `carina/adapters/__init__.py`.

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `CARINA_HOST` | `127.0.0.1` | Bind host |
| `CARINA_PORT` | `8787` | Bind port |
| `CARINA_CONFIG_DIR` | `~/.config/carina` | Config directory |
| `CARINA_HEALTH_INTERVAL` | `30` | Seconds between health probes |

---
description: "Python style and secret-handling rules for the local model-proxy backend"
applyTo: "**/*.py"
---

# Python Backend Conventions — Model Proxy

## Style & Structure
- Target Python 3.11+. Use full type hints on all public functions and `pydantic` models for I/O schemas.
- Format with `ruff format`; lint with `ruff`. No unused imports, no wildcard imports.
- Prefer `async def` for all I/O paths (proxy forwarding, provider calls); use `httpx.AsyncClient`.
- Keep modules cohesive: `server/` (HTTP + control API), `adapters/` (per-provider), `store/` (config persistence), `models/` (schemas).
- Pin dependencies with exact versions in `requirements.txt` or `pyproject.toml`; keep the set minimal.

## Adapters
- Each provider adapter implements a shared `ProviderAdapter` protocol/ABC: `forward()`, `stream()`, `validate()`.
- Normalize request/response to one internal schema; isolate provider-specific quirks inside the adapter.
- Adding a provider = one new adapter module + registry entry, no changes to the proxy core.

## Secret Handling (mandatory)
- **Never log API keys, tokens, or full auth headers.** Redact to `***` in logs, errors, and exceptions.
- Load secrets from the config store or environment — never hard-code them.
- Write config files containing secrets with `0o600` permissions; create parent dirs with `0o700`.
- Back up the config file before any overwrite; never write secrets to temp files left on disk.
- Strip credentials from any data returned by the control API unless explicitly requested.

## Errors & Reliability
- Validate provider connectivity before activation; fail closed (keep previous active provider on error).
- Set explicit timeouts on all outbound `httpx` calls; surface upstream status codes without leaking secrets.
- For streaming, propagate SSE chunks promptly and close upstream connections on client disconnect.

## Testing
- Unit-test each adapter against a mock provider; cover non-streaming and streaming paths.
- Assert that no secret appears in captured logs or serialized API responses.

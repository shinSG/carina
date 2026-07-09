# carina

A local model-service proxy with provider switching, format translation, and failover —
inspired by [cc-switch](https://github.com/farion1231/cc-switch), implemented as a Python backend.

Register multiple AI providers, pick the active one, and point your client apps at carina's
single local endpoint. carina forwards to the active provider, translating between the
**OpenAI Chat Completions** and **Anthropic Messages** formats as needed, with health checks,
auto-failover, and per-provider circuit breakers.

## Features

- Client endpoints: `POST /v1/chat/completions` (OpenAI) and `POST /v1/messages` (Anthropic)
- Cross-protocol translation (client format may differ from the provider's)
- SSE streaming on both endpoints
- Provider profiles persisted as JSON (`~/.config/carina/config.json`), `0o600`, atomic writes + backup
- One-click switch, health monitoring, auto-failover, circuit breaker
- Minimal web UI at `/` and a REST control API under `/api`
- API keys are never logged and are redacted from API responses

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
carina          # or: python -m carina
```

Open http://127.0.0.1:8787/ to manage providers, then send requests to the proxy endpoints.

### Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `CARINA_HOST` | `127.0.0.1` | Bind host (loopback only by default) |
| `CARINA_PORT` | `8787` | Bind port |
| `CARINA_CONFIG_DIR` | `~/.config/carina` | Config directory |
| `CARINA_HEALTH_INTERVAL` | `30` | Seconds between health probes |

## Control API

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/providers` | List providers (+ active id) |
| POST | `/api/providers` | Create a provider |
| GET/PUT/DELETE | `/api/providers/{id}` | Get / update / delete |
| POST | `/api/providers/{id}/activate` | Make a provider active |
| POST | `/api/providers/{id}/test` | Connectivity/credential check |
| GET | `/api/active` | Current active provider |
| GET | `/api/health` | Per-provider health + circuit state |

## Development

```bash
pytest      # run tests
ruff check  # lint
```

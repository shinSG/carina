---
description: "Generate a development plan for a local model-service proxy (cc-switch style) with a Python backend"
name: "Plan: Local Model Proxy"
argument-hint: "Optional: target providers, framework, or constraints"
agent: "plan"
---

# Plan a Local Model-Service Proxy (cc-switch style)

Produce a concrete, phased development plan for building a **local model-service proxy** whose
behavior is modeled on [cc-switch](https://github.com/farion1231/cc-switch). The **backend must be
implemented in Python**. Reference cc-switch only for *feature parity* — do not copy its code.

## Product Goal

A locally-running service that lets a user register multiple AI model providers (API endpoints +
credentials + model names) and **switch the "active" provider on demand**. Client apps point at the
proxy's single local endpoint; the proxy forwards requests to whichever provider is currently active,
translating request/response formats as needed.

## Feature Parity Reference (cc-switch)

Plan for these cc-switch capabilities, adapted to a Python backend:
- **Provider profiles**: named configs (base URL, API key, default model, request headers).
- **One-click active switch**: select which provider serves traffic; persist the choice.
- **Config persistence**: store profiles on disk (e.g. JSON/SQLite under a user config dir), with
  import/export and safe backup before overwrite.
- **Validation / connectivity test**: ping a provider before activating it.
- **Multiple protocol targets**: e.g. OpenAI-compatible, Anthropic, and a generic passthrough.

## Required Backend Capabilities (Python)

- Local HTTP proxy endpoint that forwards chat/completion requests to the active provider.
- Request/response transformation between the client-facing schema and each provider's schema.
- Streaming (SSE) passthrough for token streaming.
- Provider CRUD + activate API (REST) for a future UI to consume.
- Secret handling: keys never logged; stored with file-permission hardening.

## Plan Output Requirements

Structure the plan as:

1. **Architecture** — components (proxy server, config store, provider adapters, control API),
   a request-flow diagram (mermaid), and chosen Python stack with brief justification
   (recommend FastAPI + httpx + pydantic + uvicorn unless the user overrides via arguments).
2. **Data model** — provider profile schema and active-state persistence format.
3. **Adapter design** — how each provider protocol is normalized; how to add a new provider.
4. **Phased milestones** — each phase has a goal, deliverables, and a verifiable acceptance check.
   Suggested phases: (P0) skeleton + config store, (P1) single-provider passthrough,
   (P2) multi-provider + switch API, (P3) streaming + format translation, (P4) validation/tests/packaging.
5. **Testing strategy** — unit tests for adapters, integration test with a mock provider, streaming test.
6. **Risks & open questions** — auth/secret storage, rate limits, schema drift between providers.

## Constraints

- Backend in Python only; keep dependencies minimal and pin versions.
- Inspect the current workspace first and align the plan to any existing structure/conventions.
- Do **not** write implementation code in this step — deliver the plan as Markdown with explicit,
  checkable milestones. Note where decisions need user confirmation.

"""REST control API for managing providers, active state, and health."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from carina.adapters import build_adapter
from carina.models import ProviderCreate, ProviderUpdate
from carina.server import get_state
from carina.store import ProviderNotFoundError

router = APIRouter(prefix="/api")


@router.get("/providers")
def list_providers(state=Depends(get_state)):
    return {
        "active_id": state.store.active_id(),
        "providers": [p.redacted() for p in state.store.list_providers()],
    }


@router.post("/providers", status_code=201)
def create_provider(payload: ProviderCreate, state=Depends(get_state)):
    provider = state.store.add_provider(payload)
    return provider.redacted()


@router.get("/providers/{provider_id}")
def get_provider(provider_id: str, state=Depends(get_state)):
    try:
        return state.store.get_provider(provider_id).redacted()
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="provider not found") from exc


@router.put("/providers/{provider_id}")
def update_provider(provider_id: str, payload: ProviderUpdate, state=Depends(get_state)):
    try:
        return state.store.update_provider(provider_id, payload).redacted()
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="provider not found") from exc


@router.delete("/providers/{provider_id}", status_code=204)
def delete_provider(provider_id: str, state=Depends(get_state)):
    try:
        state.store.delete_provider(provider_id)
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="provider not found") from exc


@router.post("/providers/{provider_id}/activate")
def activate_provider(provider_id: str, state=Depends(get_state)):
    try:
        provider = state.store.set_active(provider_id)
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="provider not found") from exc
    return {"active_id": provider.id, "provider": provider.redacted()}


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str, state=Depends(get_state)):
    try:
        provider = state.store.get_provider(provider_id)
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="provider not found") from exc
    adapter = build_adapter(provider)
    try:
        ok, detail = await adapter.validate()
    except Exception as exc:  # noqa: BLE001 - report any failure to the caller
        ok, detail = False, str(exc)
    return {"ok": ok, "detail": detail}


@router.get("/active")
def get_active(state=Depends(get_state)):
    provider = state.store.active_provider()
    return {
        "active_id": state.store.active_id(),
        "provider": provider.redacted() if provider else None,
    }


@router.get("/health")
def get_health(state=Depends(get_state)):
    return {"providers": [r.model_dump(mode="json") for r in state.monitor.records()]}

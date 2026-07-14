"""JSON-backed persistence for provider profiles and active state.

Secrets are written with ``0o600`` file permissions and never logged. Writes are
atomic (temp file + ``os.replace``) and the previous config is backed up before
each overwrite.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from carina import config as cfg
from carina.models import (
    ProviderCreate,
    ProviderProfile,
    ProviderUpdate,
    ProxyConfig,
    RoutingConfig,
)


class ProviderNotFoundError(KeyError):
    """Raised when a provider id does not exist."""


class ConfigStore:
    """Thread-safe JSON store for :class:`ProxyConfig`."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or cfg.config_file()
        self._lock = threading.RLock()
        self._config = self._load()

    # --- persistence ------------------------------------------------------

    def _load(self) -> ProxyConfig:
        if not self._path.exists():
            return ProxyConfig()
        try:
            raw = self._path.read_text(encoding="utf-8")
            return ProxyConfig.model_validate_json(raw)
        except (json.JSONDecodeError, ValueError):
            # Corrupt file: keep it as a backup, start fresh.
            backup = self._path.with_suffix(self._path.suffix + ".corrupt")
            self._path.replace(backup)
            return ProxyConfig()

    def _save(self) -> None:
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Back up the previous file before overwriting.
        if self._path.exists():
            backup = self._path.with_suffix(self._path.suffix + ".bak")
            self._path.replace(backup)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = self._config.model_dump_json(indent=2)
        # Create the temp file with restrictive permissions from the start.
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        os.replace(str(tmp), str(self._path))
        os.chmod(str(self._path), 0o600)

    # --- reads ------------------------------------------------------------

    def snapshot(self) -> ProxyConfig:
        with self._lock:
            return self._config.model_copy(deep=True)

    def list_providers(self) -> list[ProviderProfile]:
        with self._lock:
            return [p.model_copy(deep=True) for p in self._config.providers]

    def get_provider(self, provider_id: str) -> ProviderProfile:
        with self._lock:
            for p in self._config.providers:
                if p.id == provider_id:
                    return p.model_copy(deep=True)
        raise ProviderNotFoundError(provider_id)

    def active_id(self) -> str | None:
        with self._lock:
            return self._config.active_id

    def active_provider(self) -> ProviderProfile | None:
        with self._lock:
            if self._config.active_id is None:
                return None
            for p in self._config.providers:
                if p.id == self._config.active_id:
                    return p.model_copy(deep=True)
            return None

    def routing_config(self) -> RoutingConfig:
        with self._lock:
            return self._config.routing.model_copy(deep=True)

    # --- writes -----------------------------------------------------------

    def add_provider(self, payload: ProviderCreate) -> ProviderProfile:
        with self._lock:
            provider = ProviderProfile(**payload.model_dump())
            self._config.providers.append(provider)
            if self._config.active_id is None:
                self._config.active_id = provider.id
            self._save()
            return provider.model_copy(deep=True)

    def update_provider(self, provider_id: str, payload: ProviderUpdate) -> ProviderProfile:
        with self._lock:
            for idx, p in enumerate(self._config.providers):
                if p.id == provider_id:
                    changes = payload.model_dump(exclude_unset=True)
                    updated = p.model_copy(update=changes)
                    self._config.providers[idx] = updated
                    self._save()
                    return updated.model_copy(deep=True)
        raise ProviderNotFoundError(provider_id)

    def delete_provider(self, provider_id: str) -> None:
        with self._lock:
            before = len(self._config.providers)
            self._config.providers = [p for p in self._config.providers if p.id != provider_id]
            if len(self._config.providers) == before:
                raise ProviderNotFoundError(provider_id)
            if self._config.active_id == provider_id:
                self._config.active_id = (
                    self._config.providers[0].id if self._config.providers else None
                )
            self._save()

    def set_active(self, provider_id: str) -> ProviderProfile:
        with self._lock:
            for p in self._config.providers:
                if p.id == provider_id:
                    self._config.active_id = provider_id
                    self._save()
                    return p.model_copy(deep=True)
        raise ProviderNotFoundError(provider_id)

    def set_routing_config(self, routing: RoutingConfig) -> RoutingConfig:
        with self._lock:
            self._config.routing = routing.model_copy(deep=True)
            self._save()
            return self._config.routing.model_copy(deep=True)

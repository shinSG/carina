"""Tests for the JSON config store: CRUD, active state, perms, backup, redaction."""

from __future__ import annotations

import os
import stat

from carina.models import ProviderCreate, ProviderUpdate
from carina.store import ConfigStore, ProviderNotFoundError


def _payload(name="p1", **kw):
    base = {"name": name, "protocol": "openai", "base_url": "https://x/v1", "api_key": "secret"}
    base.update(kw)
    return ProviderCreate(**base)


def test_add_sets_first_as_active(store):
    p = store.add_provider(_payload())
    assert store.active_id() == p.id
    assert [x.id for x in store.list_providers()] == [p.id]


def test_update_and_delete(store):
    p = store.add_provider(_payload())
    updated = store.update_provider(p.id, ProviderUpdate(name="renamed"))
    assert updated.name == "renamed"
    store.delete_provider(p.id)
    assert store.list_providers() == []
    assert store.active_id() is None


def test_delete_reassigns_active(store):
    a = store.add_provider(_payload("a"))
    b = store.add_provider(_payload("b"))
    store.set_active(a.id)
    store.delete_provider(a.id)
    assert store.active_id() == b.id


def test_missing_raises(store):
    try:
        store.get_provider("nope")
    except ProviderNotFoundError:
        pass
    else:
        raise AssertionError("expected ProviderNotFoundError")


def test_file_permissions_are_owner_only(tmp_path):
    path = tmp_path / "config.json"
    store = ConfigStore(path=path)
    store.add_provider(_payload())
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600


def test_backup_created_before_overwrite(tmp_path):
    path = tmp_path / "config.json"
    store = ConfigStore(path=path)
    store.add_provider(_payload("a"))
    store.add_provider(_payload("b"))  # second save triggers a backup
    assert (tmp_path / "config.json.bak").exists()


def test_redaction_hides_key(store):
    p = store.add_provider(_payload(api_key="topsecret"))
    red = p.redacted()
    assert red["api_key"] == "***"
    assert red["has_api_key"] is True
    assert "topsecret" not in str(red)


def test_persistence_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    s1 = ConfigStore(path=path)
    p = s1.add_provider(_payload(api_key="k"))
    s2 = ConfigStore(path=path)
    loaded = s2.get_provider(p.id)
    assert loaded.api_key == "k"
    assert s2.active_id() == p.id

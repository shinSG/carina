"""Runtime configuration and filesystem paths for carina."""

from __future__ import annotations

import os
from pathlib import Path


def config_dir() -> Path:
    """Return the user config directory for carina (``~/.config/carina`` by default).

    Honors ``CARINA_CONFIG_DIR`` and ``XDG_CONFIG_HOME`` when set.
    """
    override = os.environ.get("CARINA_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "carina"


def config_file() -> Path:
    """Return the path to the providers config JSON file."""
    return config_dir() / "config.json"


def server_host() -> str:
    """Bind host. Defaults to loopback only for safety."""
    return os.environ.get("CARINA_HOST", "127.0.0.1")


def server_port() -> int:
    """Bind port."""
    return int(os.environ.get("CARINA_PORT", "8787"))


def health_interval_s() -> float:
    """Seconds between background health checks."""
    return float(os.environ.get("CARINA_HEALTH_INTERVAL", "30"))

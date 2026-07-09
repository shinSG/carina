"""Shared dependencies for server routes."""

from __future__ import annotations

from fastapi import Request


def get_state(request: Request):
    """Return the shared :class:`AppState` for the current app."""
    return request.app.state.carina

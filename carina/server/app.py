"""FastAPI application factory and shared app state."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from carina import config as cfg
from carina.health import HealthMonitor
from carina.router import Router
from carina.store import ConfigStore

logger = logging.getLogger("carina")


class AppState:
    """Holds the singletons shared across requests."""

    def __init__(self, store: ConfigStore, monitor: HealthMonitor, router: Router) -> None:
        self.store = store
        self.monitor = monitor
        self.router = router


def create_app(store: ConfigStore | None = None, start_health: bool = True) -> FastAPI:
    store = store or ConfigStore()
    monitor = HealthMonitor(store, interval_s=cfg.health_interval_s())
    router = Router(store, monitor)
    state = AppState(store, monitor, router)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_health:
            monitor.start()
        try:
            yield
        finally:
            await monitor.stop()

    app = FastAPI(title="carina", version="0.1.0", lifespan=lifespan)
    app.state.carina = state

    from carina.server.control_routes import router as control_router
    from carina.server.proxy_routes import router as proxy_router

    app.include_router(proxy_router)
    app.include_router(control_router)

    web_dir = Path(__file__).resolve().parent.parent / "web"
    if web_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")

    return app

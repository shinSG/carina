"""Console entry point: ``python -m carina`` / ``carina``."""

from __future__ import annotations

import logging

import uvicorn

from carina import config as cfg
from carina.server.app import create_app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = create_app()
    uvicorn.run(app, host=cfg.server_host(), port=cfg.server_port())


if __name__ == "__main__":
    main()

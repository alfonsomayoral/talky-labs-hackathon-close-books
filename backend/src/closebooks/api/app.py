"""FastAPI application of CONTRACT §5."""
from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import paths
from . import errors, routes_cases, routes_data, routes_ledger, routes_runs, routes_txns
from .store import Store

LOCALHOST = r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?"


def create_app(runs_dir: Path | None = None, warm: str | None = None, store: Store | None = None) -> FastAPI:
    """`warm` is a run id to open at startup, so its first request is not the one that pays for the build."""
    store = store or Store(runs_dir or paths.RUNS, served=warm)
    store.served = warm or store.served
    warm = store.served

    def open_run(run_id: str) -> None:
        """The run and the package tables its screens read, so no first request pays for their build."""
        phase = store.phase(store.run(run_id).phase)
        phase.accounts()
        phase.ensure_items()
        phase.documents()
        phase.detail_files()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if warm:
            threading.Thread(target=open_run, args=(warm,), daemon=True).start()
        yield

    app = FastAPI(title="Close the Books", version="2.1", lifespan=lifespan)
    app.state.store = store
    app.add_middleware(CORSMiddleware, allow_origin_regex=LOCALHOST, allow_methods=["*"], allow_headers=["*"])
    errors.install(app)
    for module in (routes_runs, routes_txns, routes_cases, routes_ledger, routes_data):
        app.include_router(module.router, prefix="/api")
    return app

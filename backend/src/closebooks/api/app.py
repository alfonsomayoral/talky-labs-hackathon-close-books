"""FastAPI application of CONTRACT §5."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import paths
from . import errors, routes_cases, routes_data, routes_ledger, routes_runs, routes_txns
from .store import Store

LOCALHOST = r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?"


def create_app(runs_dir: Path | None = None, warm: str | None = None, store: Store | None = None) -> FastAPI:
    """`warm` is the served run, marked `served` in /api/runs. The caller preloads it (Store.preload) first."""
    store = store or Store(runs_dir or paths.RUNS, served=warm)
    store.served = warm or store.served

    app = FastAPI(title="Close the Books", version="2.1")
    app.state.store = store
    app.add_middleware(CORSMiddleware, allow_origin_regex=LOCALHOST, allow_methods=["*"], allow_headers=["*"])
    errors.install(app)
    for module in (routes_runs, routes_txns, routes_cases, routes_ledger, routes_data):
        app.include_router(module.router, prefix="/api")
    return app

"""Errors as application/problem+json (RFC 9457)."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class Problem(Exception):
    def __init__(self, status: int, title: str, detail: str | None = None):
        super().__init__(title)
        self.status, self.title, self.detail = status, title, detail


def not_found(what: str, ident: str) -> Problem:
    return Problem(404, f"{what} not found", f"No {what.lower()} with id {ident!r}")


def _response(status: int, title: str, detail: str | None) -> JSONResponse:
    body = {"type": "about:blank", "title": title, "status": status}
    if detail:
        body["detail"] = detail
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def install(app: FastAPI) -> None:
    @app.exception_handler(Problem)
    async def _problem(_: Request, exc: Problem):
        return _response(exc.status, exc.title, exc.detail)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        titles = {404: "Not found", 405: "Method not allowed"}
        return _response(exc.status_code, titles.get(exc.status_code, "HTTP error"), str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        detail = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:5])
        return _response(422, "Invalid request", detail)

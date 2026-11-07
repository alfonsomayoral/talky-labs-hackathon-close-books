"""Pagination, multi-value filters and multi-criteria sort over DuckDB tables."""
from __future__ import annotations

import unicodedata
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Query

from .errors import Problem


def csv(raw: str | None) -> list[str]:
    return [v for v in (s.strip() for s in raw.split(",")) if v] if raw else []


def fold(text: str) -> str:
    """Lower case without accents: what `q` compares."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


class Pagination:
    def __init__(self, page: Annotated[int, Query(ge=1)] = 1, size: Annotated[int, Query(ge=1, le=200)] = 50):
        self.page, self.size = page, size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


Paging = Annotated[Pagination, Depends()]


class Where:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.params: list = []

    def add(self, sql: str, *params) -> None:
        self.parts.append(sql)
        self.params.extend(params)

    def isin(self, column: str, raw: str | None, convert: Callable = str) -> None:
        values = csv(raw)
        if values:
            try:
                converted = [convert(v) for v in values]
            except ValueError as exc:
                raise Problem(422, "Invalid request", f"Bad value for {column}: {raw}") from exc
            self.add(f"{column} IN ({','.join('?' * len(converted))})", *converted)

    def search(self, column: str, q: str | None) -> None:
        if q and q.strip():
            self.add(f"contains({column}, ?)", fold(q.strip()))

    def clause(self) -> str:
        return "WHERE " + " AND ".join(self.parts) if self.parts else ""


def order_by(raw: str | None, allowed: dict[str, str], default: str, tiebreak: str) -> str:
    """`field` or `-field`, several separated by comma. `allowed` maps the row key to its column."""
    parts = []
    for token in csv(raw):
        desc = token.startswith("-")
        key = token.lstrip("-")
        if key not in allowed:
            raise Problem(422, "Invalid request", f"Cannot sort by {key!r}. Allowed: {', '.join(sorted(allowed))}")
        parts.append(f"{allowed[key]} {'DESC' if desc else 'ASC'} NULLS LAST")
    return "ORDER BY " + ", ".join(parts + [tiebreak]) if parts else f"ORDER BY {default}, {tiebreak}"


def fetch(cur, sql: str, params: list | None = None) -> list[dict]:
    cur.execute(sql, params or [])
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]


def page_of(cur, source: str, select: str, where: Where, order: str, paging: Pagination) -> dict:
    total = cur.execute(f"SELECT count(*) FROM {source} {where.clause()}", where.params).fetchone()[0]
    items = fetch(cur, f"SELECT {select} FROM {source} {where.clause()} {order} LIMIT ? OFFSET ?",
                  [*where.params, paging.size, paging.offset])
    return {"items": items, "total": total, "page": paging.page, "size": paging.size}

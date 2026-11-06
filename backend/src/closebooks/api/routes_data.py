"""The package of a phase: accounts, items, parties, documents and detail files. Read-only."""
from __future__ import annotations

from fastapi import APIRouter, Request

from .documents import facts_for, read_text
from .errors import Problem, not_found
from .fsafe import safe_join
from .query import Paging, Where, csv, fold, order_by, page_of
from .routes_ledger import PARTY_FIELDS
from .routes_runs import NOT_IN_QUEUE
from .schemas import Account, DataItem, DetailFileRow, DocumentDetail, DocumentRow, Paged, Party

router = APIRouter(prefix="/data/{phase}")

ITEM_FIELDS = ["itemId", "itemType", "entity", "documentNumber", "partyId", "partyName", "issueDate", "dueDate",
               "currency", "totalCents", "openAtStartCents", "relatedDocument", "reference"]
ITEM_SORT = {k: f'"{k}"' for k in ITEM_FIELDS}
PARTY_SORT = {k: f'"{k}"' for k in PARTY_FIELDS}


def _slice(rows: list[dict], paging) -> dict:
    return {"items": rows[paging.offset:paging.offset + paging.size], "total": len(rows), "page": paging.page,
            "size": paging.size}


@router.get("/accounts", response_model=list[Account])
def accounts(phase: str, request: Request, runId: str | None = None):
    store = request.app.state.store
    data = store.phase(phase)
    out = [dict(a) for a in data.accounts()]
    if runId:
        run = store.run(runId)
        if run.phase != phase:
            raise Problem(422, "Invalid request", f"Run {runId} belongs to phase {run.phase}, not {phase}")
        rates = {acc: auto / n for acc, n, auto in run.cursor().execute(
            f'SELECT "accountId", count(*), count(*) FILTER (WHERE {NOT_IN_QUEUE}) FROM tx GROUP BY 1').fetchall()}
        for a in out:
            a["reconciledRate"] = rates.get(a["accountId"])
    return out


@router.get("/items", response_model=Paged[DataItem])
def items(phase: str, request: Request, paging: Paging, type: str | None = None, entity: str | None = None,
          partyId: str | None = None, q: str | None = None, sort: str | None = None):
    data = request.app.state.store.phase(phase)
    data.ensure_items()
    w = Where()
    w.isin('"itemType"', type)
    w.isin('"entity"', entity)
    w.isin('"partyId"', partyId)
    w.search('"_search"', q)
    return page_of(data.cursor(), "items", ", ".join(f'"{f}"' for f in ITEM_FIELDS), w,
                   order_by(sort, ITEM_SORT, '"issueDate"', '"itemId"'), paging)


@router.get("/parties", response_model=Paged[Party])
def parties(phase: str, request: Request, paging: Paging, kind: str | None = None, entity: str | None = None,
            q: str | None = None, sort: str | None = None):
    data = request.app.state.store.phase(phase)
    w = Where()
    w.isin('"kind"', kind)
    w.isin('"entity"', entity)
    if q and q.strip():
        w.add("contains(strip_accents(lower(concat_ws(' ', \"partyId\", name, \"tradeName\", \"taxId\"))), ?)",
              fold(q.strip()))
    return page_of(data.cursor(), "party", ", ".join(f'"{f}"' for f in PARTY_FIELDS), w,
                   order_by(sort, PARTY_SORT, '"partyId"', '"partyId"'), paging)


def _filtered(rows: list[dict], kind: str | None, entity: str | None, q: str | None, text_fields: tuple) -> list[dict]:
    kinds, entities, needle = set(csv(kind)), set(csv(entity)), fold(q.strip()) if q and q.strip() else None
    return [r for r in rows
            if (not kinds or r["kind"] in kinds) and (not entities or r["entity"] in entities)
            and (needle is None or any(needle in fold(r[f] or "") for f in text_fields))]


@router.get("/documents", response_model=Paged[DocumentRow])
def documents(phase: str, request: Request, paging: Paging, kind: str | None = None, entity: str | None = None,
              q: str | None = None):
    rows = request.app.state.store.phase(phase).documents()
    return _slice(_filtered(rows, kind, entity, q, ("name", "partyName")), paging)


@router.get("/documents/{path:path}", response_model=DocumentDetail)
def document(phase: str, path: str, request: Request, runId: str | None = None):
    """Text and, when a run has extracted them, facts. `runId` defaults to the latest run of the phase."""
    store = request.app.state.store
    data = store.phase(phase)
    if safe_join(data.dir, path) is None:
        raise Problem(400, "Invalid path", "The path must be relative and stay inside the phase folder")
    row = next((d for d in data.documents() if d["path"] == path), None)
    if row is None:
        raise not_found("Document", path)
    run_dir = store.runs_dir / runId if runId else store.latest_run_of(phase)
    if runId:
        store.run_meta(runId)
    return {**row, "text": read_text(data.dir, path), "facts": facts_for(run_dir, path)}


@router.get("/detail-files", response_model=Paged[DetailFileRow])
def detail_files(phase: str, request: Request, paging: Paging, kind: str | None = None, entity: str | None = None):
    rows = request.app.state.store.phase(phase).detail_files()
    return _slice(_filtered(rows, kind, entity, None, ()), paging)


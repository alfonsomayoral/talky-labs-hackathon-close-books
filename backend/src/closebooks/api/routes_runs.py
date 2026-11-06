"""Runs: list, detail, stats, status, validation, uploads and launching a run."""
from __future__ import annotations

import gzip
import re
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile

from .. import paths
from ..evaluate import validate_file
from ..load import load_phase
from .errors import Problem, not_found
from .fsafe import extract_zip
from .jobs import check_ident
from .query import Where, csv, fetch
from .run_data import QUEUE, RunData
from .schemas import CreateRun, Run, RunCreated, RunStats, RunStatus, RunSummary, UploadResult, ValidationResult

router = APIRouter()
IN_QUEUE = "status IN ('" + "','".join(QUEUE) + "')"
NOT_IN_QUEUE = '("caseStatus" IS NULL OR "caseStatus" NOT IN (' + ",".join(f"'{s}'" for s in QUEUE) + "))"


def _score(meta: dict) -> dict | None:
    s = meta.get("score")
    return {k: s[k] for k in ("score", "metrics", "segments")} if s else None


def _summary(meta: dict) -> dict:
    models = meta.get("models") or {}
    return {**{k: meta[k] for k in ("runId", "phase", "createdAt", "gitCommit", "durationMs", "txns", "rows",
                                    "cases", "memoryRulesApplied")},
            "modelCalls": sum(m["calls"] for m in models.values()),
            "modelCostUsd": sum(m["costUsd"] for m in models.values()),
            "score": meta["score"]["score"] if meta.get("score") else None}


@router.get("/runs", response_model=list[RunSummary])
def list_runs(request: Request):
    store = request.app.state.store
    return [_summary(store.run_meta(r)) for r in store.run_ids()]


@router.get("/runs/{runId}", response_model=Run)
def get_run(runId: str, request: Request):
    meta = request.app.state.store.run_meta(runId)
    return {**meta, "score": _score(meta)}


@router.get("/runs/{runId}/status", response_model=RunStatus)
def run_status(runId: str, request: Request):
    check_ident(runId, "runId")
    status = request.app.state.store.jobs.status(runId)
    if status is None:
        raise not_found("Run", runId)
    return status


def compute_stats(run: RunData, entity: str | None) -> dict:
    cur = run.cursor()

    def scoped(*extra: str) -> Where:
        w = Where()
        w.isin("entity", entity)
        for e in extra:
            w.add(e)
        return w

    t = scoped()
    txns, auto, identified, total, first, last = cur.execute(
        f'SELECT count(*), count(*) FILTER (WHERE {NOT_IN_QUEUE}), '
        f'coalesce(sum(abs("amountEur")) FILTER (WHERE "hasItem"), 0), coalesce(sum(abs("amountEur")), 0), '
        f'min("bookingDate"), max("bookingDate") FROM tx {t.clause()}', t.params).fetchone()
    q = scoped(IN_QUEUE)
    queue_n, queue_eur = cur.execute(
        f'SELECT count(*), coalesce(sum("amountEur"), 0) FROM cases {q.clause()}', q.params).fetchone()
    c = scoped()
    by_status = {s: n for s, n in cur.execute(f"SELECT status, count(*) FROM cases {c.clause()} GROUP BY 1",
                                              c.params).fetchall()}
    by_kind = fetch(cur, f'SELECT kind, count(*) AS cases, sum("amountEur") AS "amountEur" FROM cases '
                         f'{q.clause()} GROUP BY 1 ORDER BY 3 DESC, 1', q.params)
    queue_by_entity = dict(cur.execute(f"SELECT entity, count(*) FROM cases {q.clause()} GROUP BY 1",
                                       q.params).fetchall())
    by_entity = [{"entity": e, "name": name or e, "txns": n, "txnsAuto": a, "reviewQueue": queue_by_entity.get(e, 0),
                  "identifiedEur": idf} for e, name, n, a, idf in cur.execute(
        f'SELECT tx.entity, any_value(en.name), count(*), count(*) FILTER (WHERE {NOT_IN_QUEUE}), '
        f'coalesce(sum(abs("amountEur")) FILTER (WHERE "hasItem"), 0) FROM tx '
        f'LEFT JOIN entities en ON en.code = tx.entity {t.clause()} '
        f'GROUP BY 1 ORDER BY 1', t.params).fetchall()]
    r = scoped()
    by_rule = fetch(cur, f'SELECT rule, count(*) AS rows, count(DISTINCT "bankTxnId") AS txns FROM rows '
                         f'{r.clause()} GROUP BY 1 ORDER BY 2 DESC, 1', r.params)
    rx = Where()
    rx.isin("r.entity", entity)
    rx.add("r.exception IS NOT NULL")
    by_exception = fetch(cur, f'SELECT r.exception AS exception, count(*) AS rows, '
                              f'coalesce(sum(abs(coalesce(r."amountEur", x."amountEur"))), 0) AS "amountEur" '
                              f'FROM rows r JOIN tx x ON x."bankTxnId" = r."bankTxnId" {rx.clause()} '
                              f'GROUP BY 1 ORDER BY 2 DESC, 1', rx.params)
    rc = Where()
    rc.isin("r.entity", entity)
    rc.add("r.category IS NOT NULL")
    by_category = fetch(cur, f'SELECT category, count(*) AS txns, coalesce(sum(abs("amountEur")), 0) AS "amountEur" '
                             f'FROM (SELECT DISTINCT r.category AS category, r."bankTxnId" AS id FROM rows r '
                             f'{rc.clause()}) d JOIN tx x ON x."bankTxnId" = d.id GROUP BY 1 ORDER BY 2 DESC, 1',
                        rc.params)
    days = {d: {"date": d, "txns": n, "txnsAuto": a, "reviewQueue": 0, "identifiedEur": idf}
            for d, n, a, idf in cur.execute(
        f'SELECT "bookingDate", count(*), count(*) FILTER (WHERE {NOT_IN_QUEUE}), '
        f'coalesce(sum(abs("amountEur")) FILTER (WHERE "hasItem"), 0) FROM tx {t.clause()} GROUP BY 1',
        t.params).fetchall()}
    for d, n in cur.execute(f'SELECT "bookingDate", count(*) FROM cases {q.clause()} GROUP BY 1', q.params).fetchall():
        if d in days:
            days[d]["reviewQueue"] = n
    return {"runId": run.id, "phase": run.phase, "entity": ",".join(csv(entity)) or None, "periodFrom": first,
            "periodTo": last, "txns": txns, "txnsAuto": auto, "identifiedEur": identified, "totalEur": total,
            "reviewQueue": queue_n, "reviewQueueEur": queue_eur, "byStatus": by_status, "byKind": by_kind,
            "byEntity": by_entity, "byRule": by_rule, "byException": by_exception, "byCategory": by_category,
            "byDay": [days[d] for d in sorted(days)], "score": _score(run.meta)}


@router.get("/runs/{runId}/stats", response_model=RunStats)
def run_stats(runId: str, request: Request, entity: str | None = None):
    return compute_stats(request.app.state.store.run(runId), entity)


@router.post("/runs/{runId}/validate", response_model=ValidationResult)
def validate_run(runId: str, request: Request):
    meta = request.app.state.store.run_meta(runId)
    submission = request.app.state.store.runs_dir / runId / "submission.csv.gz"
    if not submission.exists():
        raise not_found("Submission", runId)
    report = validate_file(submission, load_phase(meta["phase"]))
    with gzip.open(submission, "rb") as handle:
        uncompressed = sum(len(chunk) for chunk in iter(lambda: handle.read(1 << 20), b""))
    return {"ok": report["ok"], "errors": report["errors"], "sizeBytes": submission.stat().st_size,
            "uncompressedBytes": uncompressed, "rows": report["rows"] or 0, "txns": report["txnsCovered"] or 0}


@router.post("/uploads", response_model=UploadResult, status_code=201)
def upload(file: UploadFile):
    """A zip with the structure of a phase. Becomes db/<name>/ and can be run like any phase."""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(file.filename or "upload").stem).strip("-.") or "upload"
    upload_id, n = stem, 1
    while (paths.DB / upload_id).exists():
        n += 1
        upload_id = f"{stem}-{n}"
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "upload.zip"
        with archive.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        target = paths.DB / upload_id
        try:
            extract_zip(archive, target)
            _flatten_single_folder(target)
            if not (target / "bank_transactions.csv.gz").exists():
                raise Problem(422, "Not a phase", "The zip has no bank_transactions.csv.gz at its root")
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise
    return {"uploadId": upload_id, "phase": upload_id}


def _flatten_single_folder(target: Path) -> None:
    """`live.zip` often holds a single `live/` folder: its content is the phase."""
    entries = [p for p in target.iterdir() if not p.name.startswith("__MACOSX")]
    if len(entries) == 1 and entries[0].is_dir() and not (target / "bank_transactions.csv.gz").exists():
        inner = entries[0]
        for child in inner.iterdir():
            shutil.move(str(child), target / child.name)
        inner.rmdir()


@router.post("/runs", response_model=RunCreated, status_code=202)
def create_run(body: CreateRun, request: Request):
    store = request.app.state.store
    memory = None
    if body.memoryFrom:
        store.run_meta(body.memoryFrom)
        memory = store.runs_dir / body.memoryFrom / "human" / "memory_rules.jsonl"
        memory = memory if memory.exists() else None
    job = store.jobs.submit(body.phase, memory)
    return {"runId": job.run_id, "status": job.status}


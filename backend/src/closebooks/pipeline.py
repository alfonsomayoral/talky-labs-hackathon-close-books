"""One run: load -> rules -> resolve -> output -> score."""
from __future__ import annotations

import subprocess
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import orjson
import polars as pl

from .cases import build_cases
from .documents.advices import documents_frame, phase_advices, residue
from .documents.pdfs import clauses_frame, phase_clauses
from .evaluate import score_file
from .load import load_phase
from .output import write_cases, write_explanations, write_facts, write_jsonl, write_open_items, write_submission
from .paths import ROOT, RUNS
from .resolve import resolve
from .rules import propose, stateful


def _git_commit() -> str | None:
    done = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return done.stdout.strip() or None


def run_pipeline(phase_name: str, out: Path | None = None, score: bool = True) -> Path:
    started = datetime.now().astimezone()
    stages: dict[str, int] = {}
    clock = time.perf_counter()

    def lap(stage: str) -> None:
        nonlocal clock
        now = time.perf_counter()
        stages[stage] = int((now - clock) * 1000)
        clock = now

    run_id = out.name if out else f"{phase_name}-{started:%Y%m%d-%H%M%S}"
    run = out or RUNS / run_id
    run.mkdir(parents=True, exist_ok=True)

    phase = load_phase(phase_name)
    lap("load")
    advices = phase_advices(phase)
    phase_clauses(phase)
    lap("documents")
    proposals = propose(phase)
    lap("rules")
    rows, balances = resolve(phase, proposals, stateful(phase, proposals))
    lap("resolve")

    csv_bytes = write_submission(run, rows)
    write_explanations(run, rows)
    txns = {t["bank_txn_id"]: t for t in phase.txns.select(
        "bank_txn_id", "entity", "booking_date", "amount_cents", "currency", "amount_eur_cents", "text",
        "counterparty_name").iter_rows(named=True)}
    cases = build_cases(rows, txns, started.isoformat(timespec="seconds"))
    write_cases(run, cases)
    write_facts(run, pl.concat([documents_frame(advices), clauses_frame(phase_clauses(phase))]), None)
    write_open_items(run, phase, balances)
    write_jsonl(run / "questions.jsonl", [])
    write_jsonl(run / "drafts.jsonl", [])
    lap("output")

    result = None
    if score and phase.golden_path is not None:
        scored = score_file(run / "submission.csv.gz", phase_name)
        result = {k: scored[k] for k in ("score", "metrics", "segments", "ok", "errors")}
        lap("score")

    meta = {
        "runId": run_id, "phase": phase_name, "dataDir": str(phase.dir), "createdAt": started.isoformat(),
        "gitCommit": _git_commit(), "durationMs": sum(stages.values()), "stages": stages,
        "txns": phase.txns.height, "rows": len(rows), "csvBytes": csv_bytes,
        "byRule": dict(Counter(r.rule for r in rows)),
        "byException": dict(Counter(r.exception for r in rows if r.exception)),
        "byCategory": dict(Counter(r.category for r in rows if r.category)),
        "cases": dict(Counter(c["status"] for c in cases)),
        "advices": residue(advices), "models": {}, "memoryRulesApplied": 0, "score": result,
    }
    (run / "run.json").write_bytes(orjson.dumps(meta, option=orjson.OPT_INDENT_2))
    return run

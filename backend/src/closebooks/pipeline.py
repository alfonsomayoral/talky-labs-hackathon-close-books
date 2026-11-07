"""One run: load -> rules -> resolve -> output -> score."""
from __future__ import annotations

import gc
import resource
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import orjson
import polars as pl

from .cases import attach_questions, build_cases, overdue_cases
from .documents.advices import documents_frame, phase_advices, residue
from .documents.pdfs import clauses_frame, phase_clauses
from .drafts import render, top_per_template
from .evaluate import score_file
from .load import cancelled_item_ids, load_phase
from .output import write_cases, write_explanations, write_facts, write_jsonl, write_open_items, write_submission
from .paths import ROOT, RUNS
from .resolve import resolve
from .rules import propose, stateful


def _peak_rss_mb() -> int:
    """Peak of this process so far (bytes on macOS, kilobytes on Linux)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak // (1 << 20) if sys.platform == "darwin" else peak // (1 << 10)


def _git_commit() -> str | None:
    done = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return done.stdout.strip() or None


def _party_book(phase) -> tuple[dict[str, str], dict[str, str]]:
    """Name and country of every customer and supplier of the masters."""
    names, countries = {}, {}
    for table, key in (("customers", "customer_id"), ("suppliers", "supplier_id")):
        for party, name, country in phase.masters[table].select(key, "name", "country").iter_rows():
            names[party], countries[party] = name, country
    return names, countries


def _rates(phase, cutoff: str) -> dict[str, float]:
    """Units per EUR of each currency on the last day with a rate up to the cutoff."""
    fx = phase.masters["fx_rates"].filter(pl.col("date") <= cutoff).sort("date")
    return dict(fx.group_by("currency", maintain_order=True).last().select(
        "currency", pl.col("units_per_eur").cast(pl.Float64)).iter_rows())


def _overdue_inputs(phase, balances, cutoff: str) -> list[dict]:
    """Customer invoices past due at the cutoff, with their balance at the end of the phase."""
    cancelled = list(cancelled_item_ids(phase.items))
    late = phase.items.filter(pl.col("item_type") == "ARI", pl.col("due_date") < cutoff,
                              ~pl.col("item_id").is_in(cancelled))
    return [{"item_id": i, "entity": e, "party_id": p, "due_date": d, "currency": c, "open_cents": balances.open(i)}
            for i, e, p, d, c in late.select("item_id", "entity", "party_id", "due_date", "currency").iter_rows()]


def _item_info(phase, ids: list[str], names: dict[str, str]) -> dict[str, dict]:
    got = phase.items.filter(pl.col("item_id").is_in(list(set(ids))))
    return {r["item_id"]: {"number": r["document_number"], "party_name": r["party_name"] or names.get(r["party_id"]),
                           "due_date": r["due_date"], "currency": r["currency"]}
            for r in got.select("item_id", "document_number", "party_id", "party_name", "due_date",
                                "currency").iter_rows(named=True)}


def _drafts(cases, rows, phase, balances, names, countries, created_at: str) -> list[dict]:
    """The biggest cases of every template, written from fixed text. Cases get their draftId."""
    keys = {(c["bankTxnId"], c["itemIds"][0]): c["caseId"] for c in cases
            if c["kind"] == "supplier_invoice_mismatch"}
    exceptions = {keys[k]: r.exception for r in rows if (k := (r.bank_txn_id, r.item_id)) in keys}
    chosen = top_per_template(cases, exceptions)
    info = _item_info(phase, [i for c in chosen for i in c["itemIds"]], names)
    senders = dict(phase.masters["entities"].select("entity", "legal_name").iter_rows())
    pdfs = phase_clauses(phase)

    def pdf_of(item_id: str) -> str | None:
        doc = pdfs.doc_for_item(item_id)
        return f"pdfs/{doc.path}" if doc and not doc.path.startswith("pdfs/") else (doc.path if doc else None)

    drafts = []
    for case in chosen:
        facts = {"partyName": names.get(case["partyId"]), "country": countries.get(case["partyId"]), "email": None,
                 "sender": senders.get(case["entity"]),
                 "items": [{**info[i], "open_cents": balances.open(i), "pdf": pdf_of(i)}
                           for i in case["itemIds"] if i in info]}
        draft = render(case, facts, exceptions.get(case["caseId"]))
        if draft:
            case["draftId"] = f"D-{len(drafts) + 1:06d}"
            drafts.append({"draftId": case["draftId"], **draft, "createdAt": created_at})
    return drafts


def run_pipeline(phase_name: str, out: Path | None = None, score: bool = True) -> Path:
    started = datetime.now().astimezone()
    stages: dict[str, int] = {}
    peak_mb: dict[str, int] = {}
    clock = time.perf_counter()

    def lap(stage: str) -> None:
        nonlocal clock
        now = time.perf_counter()
        stages[stage] = int((now - clock) * 1000)
        peak_mb[stage] = _peak_rss_mb()
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
    engine = stateful(phase, proposals)
    rows, balances = resolve(phase, proposals, engine)
    engine.release()
    del proposals
    gc.collect()
    lap("resolve")

    csv_bytes = write_submission(run, rows)
    write_explanations(run, rows)
    txns = {t["bank_txn_id"]: t for t in phase.txns.select(
        "bank_txn_id", "entity", "booking_date", "amount_cents", "currency", "amount_eur_cents", "text",
        "counterparty_name", "counterparty_account").iter_rows(named=True)}
    created_at = started.isoformat(timespec="seconds")
    cases = build_cases(rows, txns, created_at)
    names, countries = _party_book(phase)
    cutoff = phase.txns["booking_date"].max()
    last_movement: dict[str, str] = {}
    for row in rows:
        if row.party_id:
            booked = txns[row.bank_txn_id]["booking_date"]
            last_movement[row.party_id] = max(last_movement.get(row.party_id, ""), booked)
    cases += overdue_cases(_overdue_inputs(phase, balances, cutoff), cutoff, _rates(phase, cutoff), names, created_at,
                           last_movement)
    questions = attach_questions(cases, engine.abstentions, txns, lambda ids: _item_info(phase, ids, names), names,
                                 created_at)
    drafts = _drafts(cases, rows, phase, balances, names, countries, created_at)
    write_cases(run, cases)
    write_facts(run, pl.concat([documents_frame(advices), clauses_frame(phase_clauses(phase))]), None)
    write_open_items(run, phase, balances)
    write_jsonl(run / "questions.jsonl", questions)
    write_jsonl(run / "drafts.jsonl", drafts)
    lap("output")

    result = None
    if score and phase.golden_path is not None:
        scored = score_file(run / "submission.csv.gz", phase_name)
        result = {k: scored[k] for k in ("score", "metrics", "segments", "ok", "errors")}
        lap("score")

    meta = {
        "runId": run_id, "phase": phase_name, "dataDir": str(phase.dir), "createdAt": started.isoformat(),
        "gitCommit": _git_commit(), "durationMs": sum(stages.values()), "stages": stages, "peakRssMb": peak_mb,
        "txns": phase.txns.height, "rows": len(rows), "csvBytes": csv_bytes,
        "byRule": dict(Counter(r.rule for r in rows)),
        "byException": dict(Counter(r.exception for r in rows if r.exception)),
        "byCategory": dict(Counter(r.category for r in rows if r.category)),
        "cases": dict(Counter(c["status"] for c in cases)),
        "advices": residue(advices), "models": {}, "memoryRulesApplied": 0, "score": result,
    }
    (run / "run.json").write_bytes(orjson.dumps(meta, option=orjson.OPT_INDENT_2))
    return run

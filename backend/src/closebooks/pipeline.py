"""One run: load -> rules -> resolve -> output -> score."""
from __future__ import annotations

import gc
import resource
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Iterator
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
from .memory import Memory, load_rules
from .output import allocation_writer, write_cases, write_facts, write_jsonl, write_open_items
from .paths import ROOT, RUNS, phase_dir
from .resolve import resolve
from .rules import propose, stateful


def _peak_rss_mb() -> int:
    """Peak of this process so far (bytes on macOS, kilobytes on Linux)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak // (1 << 20) if sys.platform == "darwin" else peak // (1 << 10)


def _git_commit() -> str | None:
    done = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return done.stdout.strip() or None


def _write_progress(run: Path, progress: dict) -> None:
    temporary = run / "progress.tmp"
    temporary.write_bytes(orjson.dumps(progress))
    temporary.replace(run / "progress.json")


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


def _overdue_inputs(phase, balances, cutoff: str) -> Iterator[dict]:
    """Customer invoices past due at the cutoff, with their balance at the end of the phase."""
    cancelled = list(cancelled_item_ids(phase.items))
    late = phase.items.select("item_id", "entity", "party_id", "due_date", "currency", "item_type").filter(
        pl.col("item_type") == "ARI", pl.col("due_date") < cutoff, ~pl.col("item_id").is_in(cancelled))
    return ({"item_id": i, "entity": e, "party_id": p, "due_date": d, "currency": c, "open_cents": balances.open(i)}
            for i, e, p, d, c in late.select("item_id", "entity", "party_id", "due_date", "currency").iter_rows())


def _item_info(phase, ids: list[str], names: dict[str, str]) -> dict[str, dict]:
    got = phase.items.filter(pl.col("item_id").is_in(list(set(ids))))
    return {r["item_id"]: {"number": r["document_number"], "party_name": r["party_name"] or names.get(r["party_id"]),
                           "due_date": r["due_date"], "currency": r["currency"]}
            for r in got.select("item_id", "document_number", "party_id", "party_name", "due_date",
                                "currency").iter_rows(named=True)}


def _drafts(cases, exceptions, phase, balances, names, countries, created_at: str) -> list[dict]:
    """The biggest cases of every template, written from fixed text. Cases get their draftId."""
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


def run_pipeline(phase_name: str, out: Path | None = None, score: bool = True, memory: Path | None = None) -> Path:
    """A scored run finishes its reconciliation worker before the parent loads the golden."""
    if not score or not (phase_dir(phase_name) / "golden_allocations.csv.gz").exists():
        return _reconcile(phase_name, out, memory)
    run = out or RUNS / f"{phase_name}-{datetime.now().astimezone():%Y%m%d-%H%M%S}"
    command = [sys.executable, "-m", "closebooks.cli", "run", "--phase", phase_name, "--out", str(run), "--no-score"]
    if memory is not None:
        command += ["--memory", str(memory)]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    meta = orjson.loads((run / "run.json").read_bytes())
    _write_progress(run, {"stage": "score", "stages": meta["stages"], "peakRssMb": meta["peakRssMb"]})
    clock = time.perf_counter()
    scored = score_file(run / "submission.csv.gz", phase_name)
    meta["score"] = {k: scored[k] for k in ("score", "metrics", "segments", "ok", "errors")}
    meta["stages"]["score"] = int((time.perf_counter() - clock) * 1000)
    meta["peakRssMb"]["score"] = _peak_rss_mb()
    meta["durationMs"] = sum(meta["stages"].values())
    (run / "run.json").write_bytes(orjson.dumps(meta, option=orjson.OPT_INDENT_2))
    return run


def _reconcile(phase_name: str, out: Path | None, memory: Path | None) -> Path:
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
        print(f"{phase_name}: {stage} {stages[stage] / 1000:.1f}s, peak {peak_mb[stage]} MiB", file=sys.stderr,
              flush=True)
        _write_progress(run, {"stage": stage, "stages": stages, "peakRssMb": peak_mb})

    run_id = out.name if out else f"{phase_name}-{started:%Y%m%d-%H%M%S}"
    run = out or RUNS / run_id
    run.mkdir(parents=True, exist_ok=True)

    phase = load_phase(phase_name)
    lap("load")
    advices = phase_advices(phase)
    phase_clauses(phase)
    lap("documents")
    taught = Memory(load_rules(memory))
    proposals = {**propose(phase), **taught.categories(phase)}
    lap("rules")
    engine = stateful(phase, proposals)
    engine.memory = taught if taught.rules else None
    created_at = started.isoformat(timespec="seconds")
    cases, txns, exceptions = [], {}, {}
    by_rule, by_exception, by_category = Counter(), Counter(), Counter()
    row_count = memory_applied = completed = 0
    last_movement: dict[str, str] = {}
    progress_clock = time.perf_counter()

    with allocation_writer(run) as writer:
        def receive(txn, rows):
            nonlocal row_count, memory_applied, completed, progress_clock
            writer.write(rows)
            row_count += len(rows)
            by_rule.update(r.rule for r in rows)
            by_exception.update(r.exception for r in rows if r.exception)
            by_category.update(r.category for r in rows if r.category)
            memory_applied += sum(r.rule == "MEMORY-RULE" for r in rows)
            txn_id = txn["bank_txn_id"]
            created = build_cases(rows, {txn_id: txn}, created_at)
            cases.extend(created)
            if txn_id in engine.abstentions and any(c["caseId"] == f"CASE-{txn_id}" for c in created):
                txns[txn_id] = txn
            supplier_issues = {r.item_id: r.exception for r in rows if r.item_id and r.item_id.startswith("AP")}
            for case in created:
                if case["kind"] == "supplier_invoice_mismatch":
                    exceptions[case["caseId"]] = supplier_issues[case["itemIds"][0]]
            for row in rows:
                if row.party_id:
                    last_movement[row.party_id] = max(last_movement.get(row.party_id, ""), txn["booking_date"])
            completed += 1
            if time.perf_counter() - progress_clock >= 5:
                progress_clock = time.perf_counter()
                print(f"{phase_name}: resolve {completed}/{phase.txns.height} txns, {row_count} rows, "
                      f"peak {_peak_rss_mb()} MiB", file=sys.stderr, flush=True)
                _write_progress(run,
                    {"stage": "resolve", "completedTxns": completed, "rows": row_count,
                     "totalTxns": phase.txns.height, "stages": stages,
                     "peakRssMb": peak_mb | {"resolve": _peak_rss_mb()}})

        _, balances = resolve(phase, proposals, engine, on_transaction=receive)
        csv_bytes = writer.csv_bytes
    engine.release()
    del proposals
    gc.collect()
    lap("resolve")

    names, countries = _party_book(phase)
    cutoff = phase.txns["booking_date"].max()
    cases += overdue_cases(_overdue_inputs(phase, balances, cutoff), cutoff, _rates(phase, cutoff), names, created_at,
                           last_movement)
    questions = attach_questions(cases, engine.abstentions, txns, lambda ids: _item_info(phase, ids, names), names,
                                 created_at)
    drafts = _drafts(cases, exceptions, phase, balances, names, countries, created_at)
    write_cases(run, cases)
    write_facts(run, pl.concat([documents_frame(advices), clauses_frame(phase_clauses(phase))]), None)
    write_open_items(run, phase, balances)
    write_jsonl(run / "questions.jsonl", questions)
    write_jsonl(run / "drafts.jsonl", drafts)
    lap("output")

    meta = {
        "runId": run_id, "phase": phase_name, "dataDir": str(phase.dir), "createdAt": started.isoformat(),
        "gitCommit": _git_commit(), "durationMs": sum(stages.values()), "stages": stages, "peakRssMb": peak_mb,
        "txns": phase.txns.height, "rows": row_count, "csvBytes": csv_bytes,
        "byRule": dict(by_rule), "byException": dict(by_exception), "byCategory": dict(by_category),
        "cases": dict(Counter(c["status"] for c in cases)),
        "advices": residue(advices), "models": {}, "memoryRulesApplied": memory_applied,
        "memoryRulesIgnored": taught.ignored, "score": None,
    }
    (run / "run.json").write_bytes(orjson.dumps(meta, option=orjson.OPT_INDENT_2))
    return run

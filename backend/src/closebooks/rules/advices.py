"""R2: ADVICE-CSV, -TXT, -XLSX, -PDF. A customer's remittance advice settles the items it lists (POLICIES §5.4).

Advice -> bank line: by the payment reference in the bank text, or by payer name and date; always the same entity and
the same total as the cash. The advice may arrive after the cash. Line -> item: by the printed number (with or without
prefix and leading zeros) and the gross amount. An advice that fits two bank lines, or a bank line with two advices,
is not proposed: nothing is forced."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date

import polars as pl

from ..documents.advices import Advice, normalize_number, phase_advices
from ..load import Phase
from ..model import Proposal

WINDOW = (-10, 3)  # booking date minus the date the advice was received, in days: it arrives 0-8 days after the cash
MIN_REF = 8  # shorter references (REM/1) would match anything once separators are dropped
NAME_CHARS = 10  # bank texts cut and rename payers: the first characters of the name are what survives


def _flat(text: str | None) -> str:
    return re.sub(r"[^0-9A-Z]", "", (text or "").upper())


def _number_keys(column: str) -> tuple[pl.Expr, pl.Expr]:
    """Our number as customers print it: complete, or without prefix, year and leading zeros."""
    norm = pl.col(column).str.to_uppercase().str.replace_all(r"[^0-9A-Z]", "")
    full = pl.when(norm.str.contains(r"^\d+$")).then(norm.str.strip_chars_start("0")).otherwise(norm)
    tail = norm.str.extract(r"^[A-Z]+\d{2}(\d+)$", 1).str.strip_chars_start("0")
    return full.alias("k_full"), tail.alias("k_tail")


def _pair_candidates(phase: Phase, advices: list[Advice]) -> dict[str, list[tuple[int, str]]]:
    """bank_txn_id -> [(advice index, how)] for every advice of the same entity and amount that cites the payment."""
    table = pl.DataFrame({
        "idx": range(len(advices)), "entity": [a.entity for a in advices], "total": [a.total_cents for a in advices],
        "currency": [a.currency for a in advices], "ref": [_flat(a.payment_ref) for a in advices],
        "payer": [_flat(a.payer)[:NAME_CHARS] for a in advices],
        "received": [date.fromisoformat(a.received_date) if a.received_date else None for a in advices],
    }, schema_overrides={"total": pl.Int64, "received": pl.Date, "idx": pl.Int64})
    credits = phase.txns.filter(pl.col("amount_cents") > 0).with_columns(
        pl.col("booking_date").str.to_date().alias("booked"),
        pl.concat_str(["text", "ref1", "ref2", "end_to_end_id", "remittance_info", "counterparty_name"],
                      separator=" ", ignore_nulls=True).alias("all_text"))
    cols = ["bank_txn_id", "entity", "booked", "all_text", "currency"]
    in_account = credits.select(*cols, pl.col("amount_cents").alias("cash")).join(
        table, left_on=["entity", "cash"], right_on=["entity", "total"], suffix="_adv")
    # An instructed amount in another currency is the amount of the documents (FX): the advice must say that currency.
    in_original = credits.filter(pl.col("orig_cents").is_not_null()).select(
        *cols, pl.col("orig_cents").alias("cash"), "orig_currency").join(
        table, left_on=["entity", "cash"], right_on=["entity", "total"], suffix="_adv").filter(
        pl.col("currency_adv") == pl.col("orig_currency")).drop("orig_currency")
    pairs = pl.concat([in_account, in_original], how="diagonal_relaxed")
    found: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for row in pairs.iter_rows(named=True):
        lag = (row["booked"] - row["received"]).days if row["received"] else None
        in_window = lag is not None and WINDOW[0] <= lag <= WINDOW[1]
        flat = _flat(row["all_text"])
        if len(row["ref"]) >= MIN_REF and row["ref"] in flat:
            found[row["bank_txn_id"]].append((row["idx"], "ref"))
        elif row["payer"] and row["payer"] in flat and in_window:
            found[row["bank_txn_id"]].append((row["idx"], "name"))
    return found


def _unique_pairs(found: dict[str, list[tuple[int, str]]], stats: Counter) -> dict[str, tuple[int, str]]:
    """Keep a pair only when neither side has another claim. By reference beats by name when a bank line has both."""
    chosen: dict[str, tuple[int, str]] = {}
    for txn, options in found.items():
        by_ref = [o for o in options if o[1] == "ref"]
        pool = by_ref or options
        if len({o[0] for o in pool}) > 1:
            stats["bank line with several advices"] += 1
            continue
        chosen[txn] = pool[0]
    claims = Counter(idx for idx, _ in chosen.values())
    for txn in [t for t, (idx, _) in chosen.items() if claims[idx] > 1]:
        stats["advice fitting several bank lines"] += 1
        del chosen[txn]
    return chosen


def _line_items(phase: Phase, advices: list[Advice], used: set[int]) -> dict[tuple[int, int], str]:
    """(advice index, line number) -> item_id, when the number and gross amount point to exactly one item."""
    lines = pl.DataFrame([
        (i, x.line_no, a.entity, normalize_number(x.document), abs(x.gross_cents), a.currency, x.doc_date, x.po)
        for i in used for a in [advices[i]] for x in a.lines if x.gross_cents is not None],
        schema={"idx": pl.Int64, "line_no": pl.Int64, "entity": pl.String, "key": pl.String, "gross": pl.Int64,
                "currency": pl.String, "doc_date": pl.String, "po": pl.String}, orient="row")
    entities = lines["entity"].unique().to_list()
    full, tail = _number_keys("document_number")
    items = phase.items.filter(pl.col("item_type").is_in(["ARI", "ARC"]), pl.col("entity").is_in(entities)).select(
        "item_id", "entity", "currency", pl.col("total_cents").abs().alias("total"), "issue_date",
        "customer_po", full, tail)
    found = pl.concat([
        lines.join(items, left_on=["entity", "key"], right_on=["entity", "k_full"], suffix="_item"),
        lines.join(items, left_on=["entity", "key"], right_on=["entity", "k_tail"], suffix="_item"),
    ], how="diagonal_relaxed").filter(
        pl.col("gross") == pl.col("total"),
        pl.col("currency").is_null() | (pl.col("currency") == pl.col("currency_item")),
    ).unique(["idx", "line_no", "item_id"])
    # Several items for one printed number (same tail in two customers): the invoice date and the PO decide.
    found = found.with_columns(
        ((pl.col("doc_date") == pl.col("issue_date")).cast(pl.Int8)
         + (pl.col("po") == pl.col("customer_po")).fill_null(False).cast(pl.Int8)).alias("fit"))
    best = found.filter(pl.col("fit") == pl.col("fit").max().over("idx", "line_no"))
    single = best.filter(pl.len().over("idx", "line_no") == 1)
    return {(i, n): item for i, n, item in single.select("idx", "line_no", "item_id").iter_rows()}


def match(phase: Phase) -> tuple[dict[str, Proposal], Counter]:
    advices = [a for a in phase_advices(phase).advices if a.entity and a.total_cents is not None]
    stats: Counter = Counter()
    if not advices:
        return {}, stats
    chosen = _unique_pairs(_pair_candidates(phase, advices), stats)
    resolved = _line_items(phase, advices, {idx for idx, _ in chosen.values()})
    proposals: dict[str, Proposal] = {}
    for txn, (idx, how) in chosen.items():
        advice = advices[idx]
        lines, deductions, unmapped = [], {}, 0
        for x in advice.lines:
            item = resolved.get((idx, x.line_no))
            if item is None or item in deductions or any(item == i for i, _ in lines):
                unmapped += 1
                continue
            lines.append((item, abs(x.paid_cents) if advice.closes else None))
            if x.shortfall_cents or x.deduction_cents:
                deductions[item] = (x.shortfall_cents, x.reason)
        stats[f"advice by {how}"] += 1
        stats["lines unmapped"] += unmapped
        if not lines:
            stats["advice without a mapped line"] += 1
            continue
        proposals[txn] = Proposal(
            rule=f"ADVICE-{advice.fmt.upper()}", lines=lines,
            confidence=1.0 if not unmapped and advice.closes else 0.85, reference=advice.payment_ref,
            deductions=deductions,
            sources=[{"kind": "remittanceAdvice", "ref": advice.path, "label": advice.payment_ref}])
    return proposals, stats


def propose(phase: Phase) -> dict[str, Proposal]:
    return match(phase)[0]

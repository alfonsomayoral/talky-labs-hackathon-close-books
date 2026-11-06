"""R1: FILE-PAYMENT-RUN. Our debit cites its payment file; the file lists the documents paid (POLICIES §5.3)."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

import polars as pl

from ..load import Phase, load_detail
from ..model import Proposal

MAX_DAYS_AFTER_DUE = 4
RUN_REF = re.compile(r"\b((?:PR|CF)\d{12})(?:-(\d{4}))?\b")
# A debit in N43 may cut the reference at the end of a 38-character field.
RUN_REF_CUT = re.compile(r"\b((?:PR|CF)\d{4,11}) \| (\d{1,8})\b")


def _cents(column: str) -> pl.Expr:
    return (pl.col(column).cast(pl.Float64) * 100).round().cast(pl.Int64)


def _documents(phase: Phase) -> pl.DataFrame:
    """One row per document of a payment file, with its item when the number and beneficiary identify one."""
    runs = load_detail(phase, "payment_runs")
    if runs.is_empty():
        return runs
    runs = runs.with_row_index("_row").with_columns(
        pl.col("debtor_account_id").str.slice(0, 4).alias("_payer"),
        _cents("document_amount").abs().alias("doc_cents"), _cents("transfer_amount").alias("transfer_cents"),
        pl.when(pl.col("document_type") == "CREDIT_NOTE").then(pl.lit("APC")).otherwise(pl.lit("API"))
        .alias("item_type"),
    )
    items = phase.items.filter(pl.col("item_type").is_in(["API", "APC"])).select(
        "item_id", "item_type", "entity", "party_id", "party_name", "document_number", "total_cents", "due_date")
    by_number = runs.select("_row", "document_number", "item_type", "beneficiary", "doc_cents", "_payer").join(
        items, on=["document_number", "item_type"])
    # The same supplier may repeat a number across entities: the entity that pays first, then the same amount.
    by_name = by_number.filter(pl.col("party_name") == pl.col("beneficiary")).sort(
        "_row", pl.col("entity") != pl.col("_payer"), pl.col("total_cents") != pl.col("doc_cents"), "item_id"
    ).unique("_row", keep="first", maintain_order=True)
    rest = by_number.join(by_name.select("_row"), on="_row", how="anti").filter(
        pl.col("total_cents") == pl.col("doc_cents"))
    # The beneficiary may be a factor or a renamed supplier: then number and amount must point to a single item.
    by_amount = rest.filter(pl.len().over("_row") == 1)
    # A partial payment to a factor matches no total: the number must be unique in the entity that pays.
    settled = pl.concat([by_name.select("_row"), by_amount.select("_row")])
    in_payer = by_number.join(settled, on="_row", how="anti").filter(
        pl.col("entity") == pl.col("_payer"), pl.col("total_cents") >= pl.col("doc_cents")
    ).filter(pl.len().over("_row") == 1)
    found = pl.concat([by_name, by_amount, in_payer]).select("_row", "item_id", "party_id", "due_date")
    return runs.join(found, on="_row", how="left").sort("_row")


def _reference(text: str) -> tuple[str, str | None] | None:
    match = RUN_REF.search(text)
    if match:
        return match[1], match[2]
    cut = RUN_REF_CUT.search(text)
    return (cut[1] + cut[2], None) if cut and len(cut[1] + cut[2]) == 14 else None


def propose(phase: Phase) -> dict[str, Proposal]:
    documents = _documents(phase)
    if documents.is_empty():
        return {}
    # Run and transfer ids repeat across entities (PR010021070874-0068 is in MA01 and MX01): always with the account.
    by_transfer: dict[tuple[str, str], list[dict]] = defaultdict(list)
    transfers_of_run: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    by_run: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in documents.select("run_id", "run_type", "debtor_account_id", "end_to_end_id", "beneficiary",
                                "transfer_cents", "doc_cents", "item_id", "party_id", "due_date", "currency",
                                "file").iter_rows(named=True):
        account = row["debtor_account_id"]
        by_transfer[account, row["end_to_end_id"]].append(row)
        by_run[account, row["run_id"]].append(row)
        transfers_of_run[account, row["run_id"]].setdefault(row["end_to_end_id"], row)

    used: set[tuple[str, str]] = set()
    proposals: dict[str, Proposal] = {}
    txns = phase.txns.select(
        "bank_txn_id", "account_id", "booking_date", "amount_cents", "orig_cents", "orig_currency",
        pl.concat_str(["text", "ref1", "ref2", "end_to_end_id", "remittance_info"], separator=" ", ignore_nulls=True)
        .alias("all_text"), "text")
    for txn in txns.iter_rows(named=True):
        ref = _reference(txn["all_text"])
        if ref is None:
            continue
        run_id, suffix = ref
        account = txn["account_id"]
        if suffix:
            rows = by_transfer.get((account, f"{run_id}-{suffix}"), [])
            reference = f"{run_id}-{suffix}"
        else:
            key = (account, run_id)
            rows = _rows_of_debit(txn, by_run.get(key, []), transfers_of_run.get(key, {}), by_transfer, used)
            reference = run_id
        applied: dict[str, int] = {}
        for row in rows:
            if row["item_id"]:
                applied[row["item_id"]] = applied.get(row["item_id"], 0) + row["doc_cents"]
        lines = list(applied.items())
        if not lines:
            continue
        returned = txn["amount_cents"] > 0
        proposals[txn["bank_txn_id"]] = Proposal(
            rule="FILE-PAYMENT-RETURN" if returned else "FILE-PAYMENT-RUN", lines=lines,
            party_id=rows[0]["party_id"], reference=reference, returned=returned,
            sources=[{"kind": "paymentRun", "ref": rows[0]["file"], "label": reference}])
    return proposals


def _matches(row: dict, txn: dict) -> bool:
    return row["transfer_cents"] in (abs(txn["amount_cents"]), txn["orig_cents"])


def _rows_of_debit(txn: dict, rows: list[dict], transfers: dict[str, dict], by_transfer: dict, used: set) -> list[dict]:
    """A debit citing only the run: the whole run, the documents of one due date, or one transfer of the same amount."""
    if not rows:
        return []
    target = abs(txn["amount_cents"])
    if rows[0]["run_type"] == "aggregated" and sum(t["transfer_cents"] for t in transfers.values()) == target:
        return rows
    if rows[0]["run_type"] == "confirming":
        return _due_group(txn, rows, target, by_transfer, transfers, used)
    text = txn["text"].upper()
    account = txn["account_id"]
    same = [t for e2e, t in transfers.items() if (account, e2e) not in used and _matches(t, txn)]
    named = [t for t in same if t["beneficiary"].upper()[:20] in text]
    pick = (named or same)[:1]
    if not pick:
        return []
    key = (account, pick[0]["end_to_end_id"])
    used.add(key)
    return by_transfer[key]


def _due_group(txn: dict, rows: list[dict], target: int, by_transfer: dict, transfers: dict, used: set) -> list[dict]:
    """Confirming clears one debit per maturity: the transfers whose last document falls due that day.

    The debit can be booked a few days after a non-working due date, so the sum of the group has the final word.
    """
    account = txn["account_id"]
    due_of: dict[str, str] = {}
    for row in rows:
        if row["due_date"]:
            due_of[row["end_to_end_id"]] = max(due_of.get(row["end_to_end_id"], ""), row["due_date"])
    groups: dict[str, list[str]] = defaultdict(list)
    for e2e in transfers:
        if (account, e2e) not in used and e2e in due_of:
            groups[due_of[e2e]].append(e2e)
    booked = date.fromisoformat(txn["booking_date"])
    for days_late in range(MAX_DAYS_AFTER_DUE + 1):
        group = groups.get((booked - timedelta(days=days_late)).isoformat(), [])
        if group and sum(transfers[e]["transfer_cents"] for e in group) == target:
            used.update((account, e) for e in group)
            return [row for e in group for row in by_transfer[account, e]]
    return []

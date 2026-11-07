"""R1: FILE-PAYMENT-RUN. Our debit cites its payment file; the file lists the documents paid (POLICIES §5.3)."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from itertools import combinations

import polars as pl

from ..load import Phase, load_detail
from ..model import Proposal
from .parties import normalize

MAX_DAYS_AFTER_DUE = 4
RUN_REF = re.compile(r"\b((?:PR|CF)\d{12})(?:-(\d{4}))?\b")
# A debit in N43 may cut the reference at the end of a 38-character field.
RUN_REF_CUT = re.compile(r"\b((?:PR|CF)\d{4,11}) \| (\d{1,8})\b")
REASON_CODE = re.compile(r"\b[A-Z]{2}\d{2}\b")  # ISO 20022 return reason: AC01, MD07, BE04
SUPPLIERS_IN_TEXT = re.compile(r"\b(\d{1,4}) [A-Z]")  # "8 PROVEEDORES": how many transfers the debit says it pays
MAX_LEFT_OUT = 3  # transfers of a maturity paid apart; more and the exact sum would prove little
NAME_CHARS = 20  # the bank cuts a beneficiary's name; the first characters are what survives


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
        "item_id", "item_type", "entity", "party_id", "party_name", "document_number", "total_cents", "open_cents",
        "due_date")
    wanted = runs.select("_row", "document_number", "item_type", "beneficiary", "doc_cents", "_payer")
    # Numbers repeat across suppliers: joining on the number alone is 69 M rows in TRAIN. The name settles nearly all.
    named = wanted.join(items, left_on=["document_number", "item_type", "beneficiary"],
                        right_on=["document_number", "item_type", "party_name"])
    by_name = named.sort(
        "_row", pl.col("entity") != pl.col("_payer"), pl.col("total_cents") != pl.col("doc_cents"), "item_id"
    ).unique("_row", keep="first", maintain_order=True)
    by_number = wanted.join(by_name.select("_row"), on="_row", how="anti").join(
        items, on=["document_number", "item_type"])
    rest = by_number.filter(pl.col("total_cents") == pl.col("doc_cents"))
    # The beneficiary may be a factor or a renamed supplier: then number and amount must point to a single item.
    by_amount = rest.filter(pl.len().over("_row") == 1)
    # A partial payment to a factor matches no total: the number must be unique in the entity that pays.
    settled = pl.concat([by_name.select("_row"), by_amount.select("_row")])
    in_payer = by_number.join(settled, on="_row", how="anti").filter(
        pl.col("entity") == pl.col("_payer"), pl.col("total_cents") >= pl.col("doc_cents"), pl.col("open_cents") > 0
    )
    # Tied on the number: the item whose balance is exactly what was paid, or, as a factor pays in two halves, the one
    # whose total is twice the document to the cent. Otherwise no guess.
    pays_balance = in_payer.filter(pl.col("open_cents") == pl.col("doc_cents"))
    untied = in_payer.join(pays_balance.select("_row"), on="_row", how="anti")
    pays_half = untied.filter((pl.col("total_cents") - 2 * pl.col("doc_cents")).abs() <= 1)
    untied = untied.join(pays_half.select("_row"), on="_row", how="anti")
    in_payer = pl.concat([pays_balance, pays_half, untied]).filter(pl.len().over("_row") == 1)
    keep = ("_row", "item_id", "party_id", "due_date")
    found = pl.concat([by_name.select(keep), by_amount.select(keep), in_payer.select(keep)])
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
                                "execution_date", "file").iter_rows(named=True):
        account = row["debtor_account_id"]
        by_transfer[account, row["end_to_end_id"]].append(row)
        by_run[account, row["run_id"]].append(row)
        transfers_of_run[account, row["run_id"]].setdefault(row["end_to_end_id"], row)
    sent: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for transfers in transfers_of_run.values():
        for transfer in transfers.values():
            sent[transfer["debtor_account_id"], transfer["transfer_cents"]].append(transfer)

    used: set[tuple[str, str]] = set()
    proposals: dict[str, Proposal] = {}
    txns = phase.txns.select(
        "bank_txn_id", "account_id", "booking_date", "amount_cents", "orig_cents", "orig_currency",
        pl.concat_str(["text", "ref1", "ref2", "end_to_end_id", "remittance_info"], separator=" ", ignore_nulls=True)
        .alias("all_text"), "text")
    for txn in txns.iter_rows(named=True):
        ref = _reference(txn["all_text"]) or _rejected_transfer(txn, sent)
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
        transfers = {r["end_to_end_id"]: r for r in rows}
        if not returned and len(transfers) == 1 and abs(txn["amount_cents"]) != rows[0]["transfer_cents"]:
            # Paid in another currency: if it is rejected, what comes back is what the account paid.
            sent[account, abs(txn["amount_cents"])].append(rows[0])
        proposals[txn["bank_txn_id"]] = Proposal(
            rule="FILE-PAYMENT-RETURN" if returned else "FILE-PAYMENT-RUN", lines=lines,
            party_id=rows[0]["party_id"], reference=reference, returned=returned,
            sources=[{"kind": "paymentRun", "ref": rows[0]["file"], "label": reference}])
    return proposals


def _leaving_out(candidates: list[str], transfers: dict, target: int, text: str) -> list[str] | None:
    """The bank says how many suppliers it pays and the maturity has one or two more, paid on their own: the only set of
    that many transfers whose exact sum is the debit."""
    said = SUPPLIERS_IN_TEXT.search(text or "")
    left = len(candidates) - int(said[1]) if said else 0
    if not 1 <= left <= MAX_LEFT_OUT:
        return None
    excess = sum(transfers[e]["transfer_cents"] for e in candidates) - target
    apart = [set(c) for c in combinations(candidates, left) if sum(transfers[e]["transfer_cents"] for e in c) == excess]
    return [e for e in candidates if e not in apart[0]] if len(apart) == 1 else None


def _rejected_transfer(txn: dict, sent: dict) -> tuple[str, str] | None:
    """A credit with a return reason and no reference (POLICIES §3): the one transfer of that amount, from that account
    and to the beneficiary the text names, made before it. POLICIES gives no time limit; two candidates are a tie."""
    if txn["amount_cents"] <= 0 or not REASON_CODE.search(txn["text"] or ""):
        return None
    text = normalize(txn["all_text"])
    found = [t for t in sent.get((txn["account_id"], txn["amount_cents"]), ())
             if t["execution_date"] < txn["booking_date"]
             and normalize(t["beneficiary"])[:NAME_CHARS] in text]
    if len(found) != 1:
        return None
    return found[0]["run_id"], found[0]["end_to_end_id"].removeprefix(found[0]["run_id"] + "-")


def _matches(row: dict, txn: dict) -> bool:
    return row["transfer_cents"] in (abs(txn["amount_cents"]), txn["orig_cents"])


def _rows_of_debit(txn: dict, rows: list[dict], transfers: dict[str, dict], by_transfer: dict, used: set) -> list[dict]:
    """A debit citing only the run: the whole run, the documents of one due date, or one transfer of the same amount."""
    if not rows:
        return []
    target = abs(txn["amount_cents"])
    if rows[0]["run_type"] == "aggregated":
        whole = sum(t["transfer_cents"] for t in transfers.values()) == target
        if whole or str(len(transfers)) in re.findall(r"\b\d+\b", txn["text"]):
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
    candidates: list[str] = []
    for days_late in range(MAX_DAYS_AFTER_DUE + 1):
        candidates = candidates + groups.get((booked - timedelta(days=days_late)).isoformat(), [])
        if candidates and sum(transfers[e]["transfer_cents"] for e in candidates) == target:
            used.update((account, e) for e in candidates)
            return [row for e in candidates for row in by_transfer[account, e]]
        kept = _leaving_out(candidates, transfers, target, txn["text"])
        if kept:
            used.update((account, e) for e in kept)
            return [row for e in kept for row in by_transfer[account, e]]
    # The transfers left out of their maturity are paid later, together: the only set of as many as the debit says.
    said = SUPPLIERS_IN_TEXT.search(txn["text"] or "")
    if said and 1 <= int(said[1]) <= MAX_LEFT_OUT:
        late = [e for es in groups.values() for e in es]
        sets = [c for c in combinations(late, int(said[1])) if sum(transfers[e]["transfer_cents"] for e in c) == target]
        if len(sets) == 1:
            used.update((account, e) for e in sets[0])
            return [row for e in sets[0] for row in by_transfer[account, e]]
    return []

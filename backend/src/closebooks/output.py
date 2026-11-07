"""The run folder of CONTRACT §2. Only submission.csv.gz writes decimals."""
from __future__ import annotations

import gzip
from pathlib import Path

import orjson
import polars as pl

from .load import Phase
from .model import Row
from .state import OpenBalances

CSV_HEADER = "bank_txn_id,item_id,amount,category,exception\n"

DOCUMENT_SCHEMA = {
    "docPath": pl.String, "docKind": pl.String, "entity": pl.String, "payerName": pl.String,
    "receivedDate": pl.String, "paymentRef": pl.String, "paymentDate": pl.String, "paymentTotalCents": pl.Int64,
    "currency": pl.String, "lineNo": pl.Int64, "documentNumber": pl.String, "documentNumberNorm": pl.String,
    "grossCents": pl.Int64, "deductionCents": pl.Int64, "reason": pl.String, "paidCents": pl.Int64,
    "customerPo": pl.String, "voucher": pl.String, "clause": pl.String, "clauseValue": pl.String,
    "method": pl.String, "model": pl.String, "cacheKey": pl.String,
}
PARTY_SCHEMA = {
    "bankTxnId": pl.String, "partyId": pl.String, "partyKind": pl.String, "payerName": pl.String, "how": pl.String,
    "confidence": pl.Float64, "alternatives": pl.String,
}


_HOW_BY_FAMILY = {"FILE": "file", "ADVICE": "advice", "MEMORY": "memoryRule"}


def parties_frame(rows: list[Row], txns: dict[str, dict]) -> pl.DataFrame:
    """facts/parties.parquet (CONTRACT §2.4): the party of each line that pays exactly one."""
    by_txn: dict[str, list[Row]] = {}
    for row in rows:
        if row.party_id:
            by_txn.setdefault(row.bank_txn_id, []).append(row)
    records = []
    for txn_id, lines in by_txn.items():
        if len({r.party_id for r in lines}) != 1:
            continue
        first = lines[0]
        records.append({
            "bankTxnId": txn_id, "partyId": first.party_id,
            "partyKind": "supplier" if first.item_id[:2] == "AP" else "customer",
            "payerName": txns.get(txn_id, {}).get("counterparty_name"),
            "how": _HOW_BY_FAMILY.get(first.rule.split("-")[0], "name"), "confidence": first.confidence,
            "alternatives": "[]",
        })
    return pl.DataFrame(records, schema=PARTY_SCHEMA)


def _gzip_bytes(path: Path, data: bytes) -> None:
    """mtime=0 and no file name in the header: same content, same bytes."""
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as gz:
        gz.write(data)


def _csv_line(row: Row) -> str:
    if row.item_id is None:
        return f"{row.bank_txn_id},,,{row.category},{row.exception or ''}\n"
    return f"{row.bank_txn_id},{row.item_id},{row.amount_cents // 100}.{row.amount_cents % 100:02d},," \
           f"{row.exception or ''}\n"


def write_submission(run: Path, rows: list[Row]) -> int:
    """Returns the uncompressed size: the official limit is on that number."""
    data = (CSV_HEADER + "".join(_csv_line(r) for r in rows)).encode()
    _gzip_bytes(run / "submission.csv.gz", data)
    return len(data)


def write_explanations(run: Path, rows: list[Row]) -> None:
    lines = [orjson.dumps({
        "bankTxnId": r.bank_txn_id, "itemId": r.item_id, "amountCents": r.amount_cents, "currency": r.currency,
        "category": r.category, "exception": r.exception, "rule": r.rule, "confidence": r.confidence,
        "partyId": r.party_id, "reference": r.reference, "sources": r.sources, "candidates": r.candidates,
    }) for r in rows]
    _gzip_bytes(run / "explanations.jsonl.gz", b"\n".join(lines) + b"\n")


def write_cases(run: Path, cases: list[dict]) -> None:
    _gzip_bytes(run / "cases.jsonl.gz", b"".join(orjson.dumps(c) + b"\n" for c in cases))


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_bytes(b"".join(orjson.dumps(r) + b"\n" for r in records))


def write_facts(run: Path, documents: pl.DataFrame | None, parties: pl.DataFrame | None) -> None:
    (run / "facts").mkdir(exist_ok=True)
    (documents if documents is not None else pl.DataFrame(schema=DOCUMENT_SCHEMA)).write_parquet(
        run / "facts" / "documents.parquet")
    (parties if parties is not None else pl.DataFrame(schema=PARTY_SCHEMA)).write_parquet(
        run / "facts" / "parties.parquet")


def _status(open_end: int, applied: bool, history: list[dict]) -> str:
    if history and history[-1]["exception"] == "RETURNED":
        return "returned"
    if history and history[-1]["exception"] == "SHORT_DISPUTE" and open_end > 0:
        return "disputed"
    if open_end <= 0:
        return "cleared"
    return "partial" if applied else "open"


def write_open_items(run: Path, phase: Phase, balances: OpenBalances) -> None:
    """One row per item issued in the phase, open at its start or with a movement (CONTRACT §2.5).

    Items closed in earlier phases (nothing open, no movement, not in open_at_start) are left out."""
    (run / "state").mkdir(exist_ok=True)
    touched = balances.touched()
    carried = set(phase.open_at_start["item_id"].to_list()) if phase.open_at_start is not None else set()
    keep = phase.items.filter(pl.col("item_id").is_in(list(touched.keys() | carried)) | (pl.col("open_cents") != 0))
    ids = keep["item_id"].to_list()
    starts = keep["open_cents"].to_list()
    ends = [balances.open(i) for i in ids]
    histories = [balances.history(i) for i in ids]
    applied = [sum(h["amountCents"] for h in hs if h["exception"] != "RETURNED") for hs in histories]
    keep.select(
        pl.col("item_id").alias("itemId"), pl.col("item_type").alias("itemType"), "entity",
        pl.col("party_id").alias("partyId"), pl.col("document_number").alias("documentNumber"),
        pl.col("issue_date").alias("issueDate"), pl.col("due_date").alias("dueDate"), "currency",
        pl.col("total_cents").alias("totalCents"),
    ).with_columns(
        pl.Series("openAtStartCents", starts, dtype=pl.Int64),
        pl.Series("appliedCents", applied, dtype=pl.Int64),
        pl.Series("openAtEndCents", ends, dtype=pl.Int64),
        pl.Series("status", [_status(e, bool(h), h) for e, h in zip(ends, histories, strict=True)], dtype=pl.String),
        pl.Series("history", [orjson.dumps(h).decode() for h in histories], dtype=pl.String),
    ).write_parquet(run / "state" / "open_items.parquet")

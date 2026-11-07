"""The run folder of CONTRACT §2. Only submission.csv.gz writes decimals."""
from __future__ import annotations

import gzip
import io
from collections.abc import Iterable
from itertools import chain
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


def _gzip_chunks(path: Path, chunks: Iterable[bytes]) -> int:
    """mtime=0 and no file name in the header: same content, same bytes."""
    size = 0
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as gz:
        with io.BufferedWriter(gz, buffer_size=1 << 20) as buffered:
            for chunk in chunks:
                size += buffered.write(chunk)
    return size


def _csv_line(row: Row) -> str:
    if row.item_id is None:
        return f"{row.bank_txn_id},,,{row.category},{row.exception or ''}\n"
    return f"{row.bank_txn_id},{row.item_id},{row.amount_cents // 100}.{row.amount_cents % 100:02d},," \
           f"{row.exception or ''}\n"


def write_submission(run: Path, rows: Iterable[Row]) -> int:
    """Returns the uncompressed size: the official limit is on that number."""
    return _gzip_chunks(run / "submission.csv.gz", chain([CSV_HEADER.encode()], (_csv_line(r).encode() for r in rows)))


def write_explanations(run: Path, rows: Iterable[Row]) -> None:
    lines = (orjson.dumps({
        "bankTxnId": r.bank_txn_id, "itemId": r.item_id, "amountCents": r.amount_cents, "currency": r.currency,
        "category": r.category, "exception": r.exception, "rule": r.rule, "confidence": r.confidence,
        "partyId": r.party_id, "reference": r.reference, "sources": r.sources, "candidates": r.candidates,
    }) + b"\n" for r in rows)
    _gzip_chunks(run / "explanations.jsonl.gz", lines)


def write_cases(run: Path, cases: Iterable[dict]) -> None:
    _gzip_chunks(run / "cases.jsonl.gz", (orjson.dumps(c) + b"\n" for c in cases))


def write_jsonl(path: Path, records: Iterable[dict]) -> None:
    with path.open("wb") as stream:
        for record in records:
            stream.write(orjson.dumps(record) + b"\n")


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
    keep = phase.items.filter(pl.col("item_id").is_in(list(touched | carried)) | (pl.col("open_cents") != 0))
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

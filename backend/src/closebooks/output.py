"""The run folder of CONTRACT §2. Only submission.csv.gz writes decimals."""
from __future__ import annotations

import gzip
import io
from collections.abc import Iterable
from contextlib import contextmanager
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


@contextmanager
def _gzip_stream(path: Path):
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as gz:
        with io.BufferedWriter(gz, buffer_size=1 << 20) as buffered:
            yield buffered


def _gzip_chunks(path: Path, chunks: Iterable[bytes]) -> int:
    """mtime=0 and no file name in the header: same content, same bytes."""
    with _gzip_stream(path) as buffered:
        return sum(buffered.write(chunk) for chunk in chunks)


def _csv_line(row: Row) -> str:
    if row.item_id is None:
        return f"{row.bank_txn_id},,,{row.category},{row.exception or ''}\n"
    return f"{row.bank_txn_id},{row.item_id},{row.amount_cents // 100}.{row.amount_cents % 100:02d},," \
           f"{row.exception or ''}\n"


def write_submission(run: Path, rows: Iterable[Row]) -> int:
    """Returns the uncompressed size: the official limit is on that number."""
    return _gzip_chunks(run / "submission.csv.gz", chain([CSV_HEADER.encode()], (_csv_line(r).encode() for r in rows)))


def write_explanations(run: Path, rows: Iterable[Row]) -> None:
    _gzip_chunks(run / "explanations.jsonl.gz", (_explanation(r) for r in rows))


def _explanation(r: Row) -> bytes:
    return orjson.dumps({
        "bankTxnId": r.bank_txn_id, "itemId": r.item_id, "amountCents": r.amount_cents, "currency": r.currency,
        "category": r.category, "exception": r.exception, "rule": r.rule, "confidence": r.confidence,
        "partyId": r.party_id, "reference": r.reference, "sources": r.sources, "candidates": r.candidates,
    }) + b"\n"


class AllocationWriter:
    def __init__(self, submission, explanations):
        self.submission, self.explanations = submission, explanations
        self.csv_bytes = submission.write(CSV_HEADER.encode())

    def write(self, rows: Iterable[Row]) -> None:
        for row in rows:
            self.csv_bytes += self.submission.write(_csv_line(row).encode())
            self.explanations.write(_explanation(row))


@contextmanager
def allocation_writer(run: Path):
    with _gzip_stream(run / "submission.csv.gz") as submission, \
            _gzip_stream(run / "explanations.jsonl.gz") as explanations:
        yield AllocationWriter(submission, explanations)


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
    carried = phase.open_at_start["item_id"] if phase.open_at_start is not None else pl.Series([], dtype=pl.String)
    touched = pl.Series("_touched", (balances.has_history(i) for i in phase.items["item_id"]), dtype=pl.Boolean)
    keep = phase.items.filter(touched | pl.col("item_id").is_in(carried.implode()) | (pl.col("open_cents") != 0))
    base = keep.select(
        pl.col("item_id").alias("itemId"), pl.col("item_type").alias("itemType"), "entity",
        pl.col("party_id").alias("partyId"), pl.col("document_number").alias("documentNumber"),
        pl.col("issue_date").alias("issueDate"), pl.col("due_date").alias("dueDate"), "currency",
        pl.col("total_cents").alias("totalCents"),
        pl.col("open_cents").alias("openAtStartCents"),
    )

    def with_history(batch: pl.DataFrame) -> pl.DataFrame:
        ends, applied, statuses, histories = [], [], [], []
        for item_id in batch["itemId"]:
            end = balances.open(item_id)
            history = balances.history(item_id)
            ends.append(end)
            applied.append(sum(h["amountCents"] for h in history if h["exception"] != "RETURNED"))
            statuses.append(_status(end, bool(history), history))
            histories.append(orjson.dumps(history).decode())
        return batch.with_columns(
            pl.Series("appliedCents", applied, dtype=pl.Int64),
            pl.Series("openAtEndCents", ends, dtype=pl.Int64),
            pl.Series("status", statuses, dtype=pl.String),
            pl.Series("history", histories, dtype=pl.String))

    schema = dict(base.schema) | {"appliedCents": pl.Int64, "openAtEndCents": pl.Int64,
                                  "status": pl.String, "history": pl.String}
    base.lazy().map_batches(with_history, schema=schema, streamable=True).sink_parquet(
        run / "state" / "open_items.parquet", engine="streaming", row_group_size=65_536)

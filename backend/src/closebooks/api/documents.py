"""Reading evidence from the phase folder: text of an advice or PDF, and the facts extracted from it."""
from __future__ import annotations

import csv
import io
from pathlib import Path

import duckdb
import orjson

from .fsafe import safe_join
from .sqlutil import lit

MAX_TEXT = 200_000


def read_text(phase_dir: Path, relative: str) -> str | None:
    """Text of a .txt/.csv advice, a .pdf or a .xlsx. None if the path is unsafe, missing or unreadable."""
    path = safe_join(phase_dir, relative)
    if path is None or not path.is_file():
        return None
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            from pypdf import PdfReader

            return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)[:MAX_TEXT]
        if suffix == ".xlsx":
            from openpyxl import load_workbook

            sheet = load_workbook(path, read_only=True, data_only=True).active
            out = io.StringIO()
            csv.writer(out, delimiter="\t").writerows(sheet.iter_rows(values_only=True))
            return out.getvalue()[:MAX_TEXT]
        raw = path.read_bytes()[:MAX_TEXT * 4]
        try:
            return raw.decode("utf-8")[:MAX_TEXT]
        except UnicodeDecodeError:
            return raw.decode("latin-1")[:MAX_TEXT]
    except Exception:  # a corrupt PDF is evidence we cannot show, not a server error
        return None


FACT_FIELDS = ("lineNo", "documentNumber", "documentNumberNorm", "grossCents", "deductionCents", "reason",
               "paidCents", "currency", "customerPo", "voucher", "clause", "clauseValue", "method", "model")


def facts_for(run_dir: Path | None, doc_path: str) -> list[dict]:
    """Lines of facts/documents.parquet for one document, in line order."""
    parquet = run_dir / "facts" / "documents.parquet" if run_dir else None
    if parquet is None or not parquet.exists():
        return []
    cols = ", ".join(f'"{f}"' for f in FACT_FIELDS)
    rows = duckdb.connect().execute(
        f'SELECT {cols} FROM read_parquet({lit(parquet)}) WHERE "docPath" = ? ORDER BY "lineNo"', [doc_path]
    ).fetchall()
    facts = [dict(zip(FACT_FIELDS, r, strict=True)) for r in rows]
    for fact in facts:
        raw = fact["clauseValue"]
        fact["clauseValue"] = orjson.loads(raw) if raw else None
    return facts

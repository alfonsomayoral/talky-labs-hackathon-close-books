"""Shared loaders for the analysis scripts.

Reads the official package from db/ and caches every big table as Parquet in runs/analysis/parquet/
(both folders are ignored by git). Amounts stay as Float64 here: these scripts only count and compare;
the backend will use integer cents.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "db"
PKG = DB / "bankrec-docs-and-masters"
MASTERS = PKG / "masters"
OUT = ROOT / "runs" / "analysis"
CACHE = OUT / "parquet"
PHASES = {"sample": PKG / "sample", "train": DB / "train", "live": DB / "live", "final": DB / "final"}

EXCEPTIONS = ["PARTIAL", "OVERPAYMENT", "SHORT_DISCOUNT", "SHORT_BANK_CHARGES", "SHORT_WITHHOLDING",
              "SHORT_DISPUTE", "DUPLICATE_PAYMENT", "UNIDENTIFIED", "RETURNED", "FX_DIFFERENCE"]


def phase_dir(phase: str) -> Path:
    d = PHASES[phase]
    if not d.exists():
        sys.exit(f"phase folder missing: {d}")
    return d


def table(phase: str, name: str) -> pl.DataFrame:
    """bank_transactions, ar_invoices, ap_invoices, credit_notes, golden_allocations, open_items_at_start."""
    src = phase_dir(phase) / f"{name}.csv.gz"
    if not src.exists():
        raise FileNotFoundError(src)
    dst = CACHE / phase / f"{name}.parquet"
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return pl.read_parquet(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    df = pl.read_csv(src, infer_schema_length=0)  # everything as str first: ids and numbers with leading zeros
    df = _typed(name, df)
    df.write_parquet(dst)
    return df


def _typed(name: str, df: pl.DataFrame) -> pl.DataFrame:
    floats = {"amount", "orig_amount", "net_amount", "tax_amount", "total_amount", "open_amount"}
    dates = {"booking_date", "value_date", "issue_date", "due_date"}
    casts = []
    for c in df.columns:
        if c in floats:
            casts.append(pl.col(c).cast(pl.Float64, strict=False))
        elif c in dates:
            casts.append(pl.col(c).str.to_date("%Y-%m-%d", strict=False))
        elif c == "difficulty":
            casts.append(pl.col(c).cast(pl.Int8))
    return df.with_columns(casts) if casts else df


def master(name: str) -> pl.DataFrame:
    return pl.read_csv(MASTERS / f"{name}.csv", infer_schema_length=0)


def detail_files(phase: str, kind: str) -> pl.DataFrame:
    """Concatenate direct_debit_batches / card_settlements / cheque_deposits / payment_runs with a `file` column."""
    dst = CACHE / phase / f"{kind}.parquet"
    folder = phase_dir(phase) / kind
    if dst.exists():
        return pl.read_parquet(dst)
    frames = []
    for f in sorted(folder.glob("*.csv")):
        frames.append(pl.read_csv(f, infer_schema_length=0).with_columns(pl.lit(f.name).alias("file")))
    df = pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()
    dst.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(dst)
    return df


def index_csv(phase: str, folder: str) -> pl.DataFrame:
    return pl.read_csv(phase_dir(phase) / folder / "index.csv", infer_schema_length=0)


def items(phase: str) -> pl.DataFrame:
    """All items of a phase with a common shape: item_id, item_type, entity, party_id, document_number,
    party_name, issue_date, currency, total_amount."""
    ar = table(phase, "ar_invoices").select(
        "item_id", pl.lit("ARI").alias("item_type"), "entity", pl.col("customer_id").alias("party_id"),
        pl.col("customer_name").alias("party_name"), "document_number", "issue_date", "currency", "total_amount")
    ap = table(phase, "ap_invoices").select(
        "item_id", pl.lit("API").alias("item_type"), "entity", pl.col("supplier_id").alias("party_id"),
        pl.col("supplier_name").alias("party_name"), pl.col("supplier_invoice_number").alias("document_number"), "issue_date", "currency", "total_amount")
    cn = table(phase, "credit_notes").select(
        "item_id", pl.col("item_id").str.slice(0, 3).alias("item_type"), "entity", "party_id", "party_name",
        "document_number", "issue_date", "currency", "total_amount")
    return pl.concat([ar, ap, cn])


NORM_RE = re.compile(r"[^A-Z0-9]")


def norm_expr(col: str) -> pl.Expr:
    return pl.col(col).fill_null("").str.to_uppercase().str.replace_all(r"[^A-Z0-9]", "")


def digits_expr(col: str) -> pl.Expr:
    """Longest run of digits (>= 5) of a printed number: what a customer quotes without prefix."""
    return pl.col(col).fill_null("").str.extract_all(r"\d{5,}").list.eval(pl.element().sort_by(pl.element().str.len_chars(), descending=True)).list.first()


def write_json(name: str, obj) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str))


def md_table(df: pl.DataFrame, floats: int = 1) -> str:
    cols = df.columns
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for row in df.iter_rows():
        cells = []
        for v in row:
            if isinstance(v, float):
                cells.append(f"{v:,.{floats}f}")
            elif isinstance(v, int):
                cells.append(f"{v:,}")
            else:
                cells.append("" if v is None else str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def section(title: str) -> None:
    print(f"\n### {title}\n")

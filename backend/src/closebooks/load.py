"""One phase of the package as Polars tables. Amounts in integer cents, always with their currency."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import polars as pl

from .paths import masters_dir, phase_dir

ITEM_COLUMNS = ["item_id", "item_type", "entity", "party_id", "party_name", "document_number", "issue_date",
                "due_date", "currency", "total_cents", "open_cents", "payment_terms", "customer_po",
                "payment_method", "related_document", "reason"]
# A phase can cite what happened before it: documents of the months before, items closed earlier.
PRIOR_PHASES = {"live": ["train"], "final": ["train", "live"]}
PRIOR_ITEM_DAYS = 2 * 366
PRIOR_DETAIL_MONTHS = 3
MONTH_IN_NAME = re.compile(r"_(\d{6})(?:_\d+)?\.")
MASTER_FILES = ("entities", "bank_accounts", "customers", "suppliers", "categories", "payment_terms", "fx_rates")


def to_cents(values: pl.Series) -> pl.Series:
    return (values.cast(pl.Float64) * 100).round().cast(pl.Int64)


def _cents(column: str) -> pl.Expr:
    return (pl.col(column).cast(pl.Float64) * 100).round().cast(pl.Int64)


def load_table(path: Path) -> pl.DataFrame:
    """Everything as text first: ids and numbers keep their leading zeros."""
    return pl.read_csv(path, infer_schema_length=0)


@dataclass
class Phase:
    name: str
    dir: Path
    masters: dict[str, pl.DataFrame]
    txns: pl.DataFrame
    items: pl.DataFrame
    open_at_start: pl.DataFrame | None
    prior: list[Path] = field(default_factory=list)
    start: str = ""

    @property
    def golden_path(self) -> Path | None:
        path = self.dir / "golden_allocations.csv.gz"
        return path if path.exists() else None


def load_masters(phase: Path) -> dict[str, pl.DataFrame]:
    folder = masters_dir(phase)
    return {name: load_table(folder / f"{name}.csv") for name in MASTER_FILES}


def _with_eur(txns: pl.DataFrame, fx_rates: pl.DataFrame) -> pl.DataFrame:
    """amount_eur_cents at the reference rate of the day (weekends and holidays: last available rate)."""
    rates = fx_rates.select(
        pl.col("date").str.to_date(), "currency", pl.col("units_per_eur").cast(pl.Float64).alias("rate")
    ).sort("date")
    keyed = txns.with_columns(pl.col("booking_date").str.to_date().alias("_date")).sort("_date")
    joined = keyed.join_asof(rates, left_on="_date", right_on="date", by="currency", strategy="backward",
                            check_sortedness=False)
    rate = pl.when(pl.col("currency") == "EUR").then(1.0).otherwise(pl.col("rate").fill_null(1.0))
    return joined.with_columns(
        (pl.col("amount_cents") / rate).round().cast(pl.Int64).alias("amount_eur_cents")
    ).drop("_date", "rate")


def _load_txns(folder: Path, fx_rates: pl.DataFrame) -> pl.DataFrame:
    txns = load_table(folder / "bank_transactions.csv.gz").with_columns(
        _cents("amount").alias("amount_cents"), _cents("orig_amount").alias("orig_cents")
    )
    return _with_eur(txns, fx_rates).sort("booking_date", "bank_txn_id")


def _issued_items(folder: Path) -> pl.DataFrame:
    ar = load_table(folder / "ar_invoices.csv.gz").select(
        "item_id", pl.lit("ARI").alias("item_type"), "entity", pl.col("customer_id").alias("party_id"),
        pl.col("customer_name").alias("party_name"), "document_number", "issue_date", "due_date", "currency",
        _cents("total_amount").alias("total_cents"), "payment_terms", "customer_po", "payment_method",
        pl.lit(None, pl.String).alias("related_document"), pl.lit(None, pl.String).alias("reason"))
    ap = load_table(folder / "ap_invoices.csv.gz").select(
        "item_id", pl.lit("API").alias("item_type"), "entity", pl.col("supplier_id").alias("party_id"),
        pl.col("supplier_name").alias("party_name"), pl.col("supplier_invoice_number").alias("document_number"),
        "issue_date", "due_date", "currency", _cents("total_amount").alias("total_cents"), "payment_terms",
        pl.col("our_po").alias("customer_po"), "payment_method",
        pl.lit(None, pl.String).alias("related_document"), pl.lit(None, pl.String).alias("reason"))
    notes = load_table(folder / "credit_notes.csv.gz").select(
        "item_id", pl.col("item_id").str.slice(0, 3).alias("item_type"), "entity", "party_id", "party_name",
        "document_number", "issue_date", pl.lit(None, pl.String).alias("due_date"), "currency",
        _cents("total_amount").alias("total_cents"), pl.lit(None, pl.String).alias("payment_terms"),
        pl.lit(None, pl.String).alias("customer_po"), pl.lit(None, pl.String).alias("payment_method"),
        "related_document", "reason")
    return pl.concat([ar, ap, notes]).with_columns(pl.col("total_cents").alias("open_cents"))


def _open_at_start(folder: Path) -> pl.DataFrame | None:
    path = folder / "open_items_at_start.csv.gz"
    if not path.exists():
        return None
    return load_table(path).with_columns(
        _cents("total_amount").alias("total_cents"), _cents("open_amount").alias("open_cents"))


def _merge_open(issued: pl.DataFrame, opening: pl.DataFrame | None) -> pl.DataFrame:
    """Items of the phase plus those carried over open. An item in both keeps its opening balance."""
    if opening is None:
        return issued.select(ITEM_COLUMNS)
    carried = opening.join(issued.select("item_id"), on="item_id", how="anti").select(
        "item_id", "item_type", "entity", "party_id", pl.lit(None, pl.String).alias("party_name"), "document_number",
        "issue_date", "due_date", "currency", "total_cents", "open_cents",
        pl.lit(None, pl.String).alias("payment_terms"), pl.lit(None, pl.String).alias("customer_po"),
        pl.lit(None, pl.String).alias("payment_method"), pl.lit(None, pl.String).alias("related_document"),
        pl.lit(None, pl.String).alias("reason"))
    balances = opening.select("item_id", pl.col("open_cents").alias("_open"))
    updated = issued.join(balances, on="item_id", how="left").with_columns(
        pl.coalesce("_open", "open_cents").alias("open_cents")).drop("_open")
    return pl.concat([updated.select(ITEM_COLUMNS), carried.select(ITEM_COLUMNS)])


def load_detail(phase: Phase, folder: str) -> pl.DataFrame:
    """All files of a detail folder as text, each row with the relative path of its file."""
    files = sorted((phase.dir / folder).glob("*.csv"))
    start = getattr(phase, "start", "")
    if start:
        first, last = _months_before(start)
        for prior in getattr(phase, "prior", []):
            files += [f for f in sorted((prior / folder).glob("*.csv"))
                      if (m := MONTH_IN_NAME.search(f.name)) and first <= m[1] <= last]
    if not files:
        return pl.DataFrame()
    return pl.concat([load_table(f).with_columns(pl.lit(f"{folder}/{f.name}").alias("file")) for f in files],
                     how="diagonal_relaxed")


def _months_before(start: str) -> tuple[str, str]:
    """YYYYMM of the first and last month of the window of detail files read from earlier phases."""
    year, month = int(start[:4]), int(start[5:7])
    index = year * 12 + month - 1
    first = index - PRIOR_DETAIL_MONTHS
    last = index - 1
    return f"{first // 12}{first % 12 + 1:02d}", f"{last // 12}{last % 12 + 1:02d}"


def cancelled_item_ids(items: pl.DataFrame) -> set[str]:
    """POLICIES §5.7: a cancelled invoice and its cancelling credit note are never settled by bank."""
    notes = items.filter(pl.col("item_type") == "ARC", pl.col("reason") == "Anulación de factura")
    invoices = items.filter(pl.col("item_type") == "ARI").join(
        notes.select("entity", pl.col("related_document").alias("document_number")).unique(),
        on=["entity", "document_number"])
    return set(notes["item_id"].to_list()) | set(invoices["item_id"].to_list())


def prior_dirs(folder: Path, name: str) -> list[Path]:
    """Earlier phases on disk. A built phase declares them in a file prior_phases; an uploaded one may have none."""
    declared = folder / "prior_phases"
    names = declared.read_text().split() if declared.exists() else PRIOR_PHASES.get(name, [])
    found = []
    for prior in names:
        try:
            found.append(phase_dir(prior))
        except FileNotFoundError:
            continue
    return found


def _with_prior_items(items: pl.DataFrame, prior: list[Path], start: str) -> pl.DataFrame:
    """Carried items recover name and terms from their phase; items closed before the phase exist with 0 open."""
    if not prior or not start:
        return items
    since = (date.fromisoformat(start) - timedelta(days=PRIOR_ITEM_DAYS)).isoformat()
    older = pl.concat([_issued_items(folder) for folder in prior]).filter(pl.col("issue_date") < start).unique(
        "item_id", keep="last")
    details = ["party_name", "payment_terms", "customer_po", "payment_method", "related_document", "reason"]
    filled = items.join(older.select("item_id", *[pl.col(c).alias(f"_{c}") for c in details]), on="item_id", how="left")
    filled = filled.with_columns([pl.coalesce(c, f"_{c}").alias(c) for c in details]).select(ITEM_COLUMNS)
    closed = older.filter(pl.col("issue_date") >= since).join(items.select("item_id"), on="item_id", how="anti")
    return pl.concat([filled, closed.with_columns(pl.lit(0, pl.Int64).alias("open_cents")).select(ITEM_COLUMNS)])


def phase_items(name: str) -> pl.DataFrame:
    folder = phase_dir(name)
    return _merge_open(_issued_items(folder), _open_at_start(folder))


def load_phase(name: str) -> Phase:
    folder = phase_dir(name)
    masters = load_masters(folder)
    opening = _open_at_start(folder)
    txns = _load_txns(folder, masters["fx_rates"])
    start = txns["booking_date"].min()
    prior = prior_dirs(folder, name)
    items = _with_prior_items(_merge_open(_issued_items(folder), opening), prior, start)
    return Phase(name=name, dir=folder, masters=masters, txns=txns, items=items, open_at_start=opening, prior=prior,
                 start=start)

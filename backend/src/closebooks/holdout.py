"""db/holdout/: TRAIN cut at a date with the shape of FINAL, and db/holdout-drift/ with drift applied (PLAN §4).

The computed opening balances live only here, to rehearse FINAL. A run of LIVE or FINAL starts from the official
open_items_at_start, never from this.
"""
from __future__ import annotations

import gzip
import re
import shutil
from pathlib import Path

import polars as pl

from .load import cancelled_item_ids, load_table, phase_items
from .paths import DB, PKG, phase_dir

CUT = "2024-12-31"
START = "2025-01-01"
END = "2025-06-30"
UNKNOWN_BEFORE = "2021-07-01"
DETAIL_FOLDERS = ("direct_debit_batches", "card_settlements", "cheque_deposits", "payment_runs")
MONTH_IN_NAME = re.compile(r"_(\d{6})(?:_\d+)?\.")

OLD_ENTITY = "MA01"
NEW_ENTITY = "ZA01"
OLD_CURRENCY = "MAD"
NEW_CURRENCY = "ZAR"
FACTOR = 2  # an integer factor keeps every sum of a remittance exact after changing currency
OLD_NUMBER_IN_TEXT = r"\b(FA|AV)(\d{9})\b"

STILL_OPEN_AFTER = ("PARTIAL", "SHORT_DISPUTE", "RETURNED")


def open_items_at(items: pl.DataFrame, golden: pl.DataFrame, cut: str, unknown_before: str) -> pl.DataFrame:
    """Balance at the cut, from the golden.

    total - amounts, RETURNED add back, DUPLICATE_PAYMENT don't count; a RETURNED of a payment made before the data
    starts must not push it above the total. An item whose last row leaves nothing open (POLICIES §3), or whose
    advance covers the rest, is closed even if older payments are unknown. Items issued before unknown_before and
    never allocated have no known state (ANALYSIS §2): excluded.

    Measured against the official file of LIVE (test_opening_balances_reproduce_...): these rules took us from 349 k
    items to 321,456 against 325,419, with 26 extra and 77 different. Cancelled items never open: the caller removes
    them (cancelled_item_ids). The 3,989 missing, of 2021-03..06, are unknown opening state: not reproducible.
    """
    past = golden.filter(pl.col("booking_date") <= cut)
    if "segment" not in past.columns:
        past = past.with_columns(pl.lit(None, pl.String).alias("segment"))
    moved = past.group_by("item_id").agg(
        pl.when(pl.col("exception") == "RETURNED").then(-pl.col("amount_cents"))
        .when(pl.col("exception") == "DUPLICATE_PAYMENT").then(0)
        .otherwise(pl.col("amount_cents")).sum().alias("_applied"),
        pl.col("exception").sort_by("booking_date", maintain_order=True).last().alias("_last"),
        (pl.col("segment") == "ar_advance_deduction").any().alias("_advance"),
    )
    ever_allocated = golden.select("item_id").unique().with_columns(pl.lit(True).alias("_known"))
    settled = pl.col("_last").is_not_null() & ~pl.col("_last").is_in(STILL_OPEN_AFTER)
    closed = settled | pl.col("_advance").fill_null(False)
    balance = (pl.col("total_cents") - pl.col("_applied").fill_null(0)).clip(upper_bound=pl.col("total_cents"))
    return (
        items.filter(pl.col("issue_date") <= cut)
        .join(moved, on="item_id", how="left")
        .join(ever_allocated, on="item_id", how="left")
        .filter(pl.col("_known").is_not_null() | (pl.col("issue_date") >= unknown_before))
        .with_columns(pl.when(closed).then(0).otherwise(balance).alias("open_cents"))
        .filter(pl.col("open_cents") > 0)
        .drop("_applied", "_last", "_advance", "_known")
    )


def _write_gz(df: pl.DataFrame, path: Path) -> None:
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        gz.write(df.write_csv().encode())


def _link(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(source.resolve())


def _fresh(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def _link_months(source: Path, target: Path) -> None:
    first, last = START[:4] + START[5:7], END[:4] + END[5:7]
    for file in sorted(source.rglob("*")):
        match = MONTH_IN_NAME.search(file.name)
        if file.is_file() and match and first <= match[1] <= last:
            _link(file, target / file.relative_to(source))


def _link_indexed(source: Path, target: Path, date_column: str) -> None:
    index = load_table(source / "index.csv").filter(pl.col(date_column).is_between(pl.lit(START), pl.lit(END)))
    target.mkdir(parents=True)
    index.write_csv(target / "index.csv")
    for name in index["file"].to_list():
        _link(source / name, target / name)


def _text_amount(cents: pl.Expr) -> pl.Expr:
    return (cents // 100).cast(pl.String) + "." + (cents % 100).cast(pl.String).str.zfill(2)


def build_holdout(dest: Path | None = None) -> Path:
    """TRAIN cut at 2024-12-31: six months with computed opening balances, shaped like FINAL."""
    train = phase_dir("train")
    out = _fresh(dest or DB / "holdout")

    all_txns = load_table(train / "bank_transactions.csv.gz")
    txns = all_txns.filter(pl.col("booking_date").is_between(pl.lit(START), pl.lit(END)))
    _write_gz(txns, out / "bank_transactions.csv.gz")
    for name in ("ar_invoices", "ap_invoices", "credit_notes"):
        table = load_table(train / f"{name}.csv.gz").filter(pl.col("issue_date").is_between(pl.lit(START), pl.lit(END)))
        _write_gz(table, out / f"{name}.csv.gz")

    golden = load_table(train / "golden_allocations.csv.gz")
    _write_gz(golden.join(txns.select("bank_txn_id"), on="bank_txn_id"), out / "golden_allocations.csv.gz")

    items = phase_items("train")
    moves = golden.filter(pl.col("item_id").is_not_null()).join(
        all_txns.select("bank_txn_id", "booking_date"), on="bank_txn_id"
    ).with_columns((pl.col("amount").cast(pl.Float64) * 100).round().cast(pl.Int64).alias("amount_cents"),
                   pl.col("exception").fill_null(""))
    candidates = items.filter(~pl.col("item_id").is_in(list(cancelled_item_ids(items))))
    opening = open_items_at(candidates, moves, cut=CUT, unknown_before=UNKNOWN_BEFORE)
    _write_gz(opening.select(
        "item_id", "item_type", "entity", "party_id", "document_number", "issue_date", "due_date", "currency",
        _text_amount(pl.col("total_cents")).alias("total_amount"),
        _text_amount(pl.col("open_cents")).alias("open_amount"),
    ).sort("item_id"), out / "open_items_at_start.csv.gz")

    for folder in (*DETAIL_FOLDERS, "bank_statements"):
        _link_months(train / folder, out / folder)
    _link_indexed(train / "remittance_advices", out / "remittance_advices", "received_date")
    _link_indexed(train / "pdfs", out / "pdfs", "document_date")
    return out


def _doubled(column: str, when: pl.Expr) -> pl.Expr:
    cents = (pl.col(column).cast(pl.Float64) * 100 * FACTOR).round().cast(pl.Int64)
    present = when & pl.col(column).is_not_null()
    return pl.when(present).then(_text_amount(cents)).otherwise(pl.col(column)).alias(column)


def _new_account(column: str = "account_id") -> pl.Expr:
    return (pl.col(column).str.replace(f"{OLD_ENTITY}-LORV-{OLD_CURRENCY}", f"{NEW_ENTITY}-UMVC-{NEW_CURRENCY}")
            .str.replace(f"{OLD_ENTITY}-LORV", f"{NEW_ENTITY}-UMVC").alias(column))


def _new_currency(when: pl.Expr, column: str = "currency") -> pl.Expr:
    return pl.when(when).then(pl.lit(NEW_CURRENCY)).otherwise(pl.col(column)).alias(column)


def _new_entity(column: str = "entity") -> pl.Expr:
    return pl.col(column).str.replace(OLD_ENTITY, NEW_ENTITY)


def clone_entity(df: pl.DataFrame, amount_cols: list[str], number_cols: list[str]) -> pl.DataFrame:
    """Turn the rows of the old entity into the new one: its ids, its numbering "KWI..." and its currency."""
    is_old = pl.col("entity") == OLD_ENTITY
    in_old_currency = is_old & (pl.col("currency") == OLD_CURRENCY)
    exprs = [_doubled(c, in_old_currency) for c in amount_cols]
    exprs += [pl.when(is_old).then(pl.col(c).str.replace(r"^(FA|AV)(\d+)$", "KWI$2")).otherwise(pl.col(c)).alias(c)
              for c in number_cols]
    exprs += [_new_entity(c) for c in ("customer_id", "supplier_id", "party_id") if c in df.columns]
    return df.with_columns(exprs).with_columns(_new_currency(in_old_currency), _new_entity())


def bank_to_camt(txns: pl.DataFrame, bank: str, since: str) -> pl.DataFrame:
    """A bank migrates from N43 to camt.053: its N43 code survives in bank_subcode (as Banco del Moncayo does)."""
    moved = (pl.col("bank") == bank) & (pl.col("booking_date") >= since)
    code = pl.when(pl.col("amount_cents") > 0).then(pl.lit("PMNT/RCDT/ESCT")).otherwise(pl.lit("PMNT/ICDT/ESCT"))
    subcode = pl.col("bank_code") + pl.col("bank_subcode").fill_null("")
    return txns.with_columns(
        pl.when(moved).then(pl.lit("camt053")).otherwise(pl.col("statement_format")).alias("statement_format"),
        pl.when(moved).then(code).otherwise(pl.col("bank_code")).alias("bank_code"),
        pl.when(moved).then(subcode).otherwise(pl.col("bank_subcode")).alias("bank_subcode"),
        pl.when(moved).then(pl.col("text")).otherwise(pl.col("remittance_info")).alias("remittance_info"),
    )


def _clone_txns(txns: pl.DataFrame) -> pl.DataFrame:
    is_old = pl.col("entity") == OLD_ENTITY
    in_old_currency = is_old & (pl.col("currency") == OLD_CURRENCY)
    orig_in_old = is_old & (pl.col("orig_currency") == OLD_CURRENCY)
    renumber = {c: pl.col(c).str.replace_all(OLD_NUMBER_IN_TEXT, "KWI$2") for c in ("text", "remittance_info")}
    return txns.with_columns(
        _doubled("amount", in_old_currency),
        _doubled("orig_amount", orig_in_old),
        _new_currency(orig_in_old, "orig_currency"),
        _new_currency(in_old_currency),
        pl.when(is_old).then(_new_account()).otherwise(pl.col("account_id")).alias("account_id"),
        pl.when(is_old).then(pl.lit("UMVC")).otherwise(pl.col("bank")).alias("bank"),
        *[pl.when(is_old).then(expr).otherwise(pl.col(c)).alias(c) for c, expr in renumber.items()],
        _new_entity(),
    )


def _clone_detail_file(source: Path, target: Path) -> None:
    """Detail file of the old entity: amounts in the new currency, invoice numbers renumbered, new account."""
    table = load_table(source)
    in_old = pl.col("currency") == OLD_CURRENCY
    amounts = ("batch_total", "amount", "gross", "fee", "net", "deposit_total", "transfer_amount", "document_amount")
    exprs = [_doubled(c, in_old) for c in amounts if c in table.columns]
    exprs += [pl.col(c).str.replace_all(OLD_NUMBER_IN_TEXT, "KWI$2") for c in
              ("remittance_info", "stub_reference", "document_number") if c in table.columns]
    exprs += [_new_account(c) for c in ("account_id", "debtor_account_id") if c in table.columns]
    target.parent.mkdir(parents=True, exist_ok=True)
    table.with_columns(*exprs, _new_currency(in_old)).write_csv(target)


def _masters_final(out: Path, renamed_every: int = 10) -> None:
    """New entity, its accounts and parties only here; every tenth customer renamed (invoices keep the old name)."""
    source = PKG / "masters"
    target = out / "masters_final"
    target.mkdir()
    for name in ("categories", "payment_terms", "fx_rates"):
        shutil.copy(source / f"{name}.csv", target / f"{name}.csv")
    old = pl.col("entity") == OLD_ENTITY
    load_table(source / "entities.csv").with_columns(
        pl.when(old).then(pl.lit("ZA")).otherwise(pl.col("country")).alias("country"),
        pl.when(old).then(pl.lit(NEW_CURRENCY)).otherwise(pl.col("functional_currency")).alias("functional_currency"),
        _new_entity(),
    ).write_csv(target / "entities.csv")
    load_table(source / "bank_accounts.csv").with_columns(
        pl.when(old).then(_new_account()).otherwise(pl.col("account_id")).alias("account_id"),
        pl.when(old).then(pl.lit("UMVC")).otherwise(pl.col("bank")).alias("bank"),
        _new_currency(old & (pl.col("currency") == OLD_CURRENCY)),
        _new_entity(),
    ).write_csv(target / "bank_accounts.csv")
    renamed = pl.lit("Nueva Marca ") + pl.col("name")
    load_table(source / "customers.csv").sort("customer_id").with_row_index("_n").with_columns(
        pl.when(pl.col("_n") % renamed_every == 0).then(renamed).otherwise(pl.col("name")).alias("name"),
        _new_entity("customer_id"), _new_entity("group_id"), _new_entity("parent_customer_id"), _new_entity(),
    ).drop("_n").write_csv(target / "customers.csv")
    load_table(source / "suppliers.csv").with_columns(_new_entity("supplier_id"), _new_entity()).write_csv(
        target / "suppliers.csv")


def _slow_receipts(txns: pl.DataFrame, slow_ids: pl.DataFrame, days: int = 15) -> pl.DataFrame:
    """Plain 1:1 receipts booked later, within the phase (their label does not depend on the date)."""
    marked = txns.join(slow_ids.with_columns(pl.lit(True).alias("_slow")), on="bank_txn_id", how="left")
    shift = pl.duration(days=days)
    later = (pl.col("booking_date").str.to_date() + shift).dt.strftime("%Y-%m-%d")
    later_value = (pl.col("value_date").str.to_date() + shift).dt.strftime("%Y-%m-%d")
    moves = pl.col("_slow").fill_null(False) & (later <= END)
    return marked.with_columns(
        pl.when(moves).then(later).otherwise(pl.col("booking_date")).alias("booking_date"),
        pl.when(moves).then(later_value).otherwise(pl.col("value_date")).alias("value_date"),
    ).drop("_slow")


def build_drift(dest: Path | None = None) -> Path:
    """The holdout with drift: ZA01 from MA01, RIBA N43 -> camt, renamed customers, new IT01 account, slower payers.

    Not yet: the top payers' advices rewritten to the new xlsx layout (PLAN §4 d), which needs the advice parsers
    of P2. Advices and PDFs of the new entity keep their original numbering.
    """
    source = phase_dir("holdout")
    out = _fresh(dest or DB / "holdout-drift")

    golden = load_table(source / "golden_allocations.csv.gz")
    plain = golden.filter(pl.col("segment").is_in(["ar_1to1", "ar_ref_noise"]), pl.col("exception").is_null())

    txns = _clone_txns(load_table(source / "bank_transactions.csv.gz")).with_columns(
        (pl.col("amount").cast(pl.Float64) * 100).round().cast(pl.Int64).alias("amount_cents"))
    txns = bank_to_camt(txns, "RIBA", "2025-04-01").drop("amount_cents")
    plain_ids = plain.select("bank_txn_id").unique()
    moved = pl.col("bank_txn_id").is_in(plain_ids["bank_txn_id"].to_list()) & (pl.col("account_id") == "IT01-VALD-EUR")
    txns = txns.with_columns(pl.when(moved & (pl.col("booking_date") >= "2025-04-01")).then(pl.lit("IT01-VALD-EUR-3"))
                             .otherwise(pl.col("account_id")).alias("account_id"))
    _write_gz(_slow_receipts(txns, plain_ids), out / "bank_transactions.csv.gz")

    in_old_currency = []
    for name, numbers in (("ar_invoices", ["document_number"]), ("ap_invoices", []),
                          ("credit_notes", ["document_number", "related_document"])):
        table = load_table(source / f"{name}.csv.gz")
        in_old_currency.append(table.filter(pl.col("entity") == OLD_ENTITY, pl.col("currency") == OLD_CURRENCY)
                               .select("item_id"))
        _write_gz(clone_entity(table, ["net_amount", "tax_amount", "total_amount"], numbers), out / f"{name}.csv.gz")
    opening = load_table(source / "open_items_at_start.csv.gz")
    in_old_currency.append(opening.filter(pl.col("entity") == OLD_ENTITY, pl.col("currency") == OLD_CURRENCY)
                           .select("item_id"))
    _write_gz(clone_entity(opening, ["total_amount", "open_amount"], ["document_number"]),
              out / "open_items_at_start.csv.gz")

    doubled = pl.concat(in_old_currency)["item_id"].to_list()
    _write_gz(golden.with_columns(_doubled("amount", pl.col("item_id").is_in(doubled))),
              out / "golden_allocations.csv.gz")

    for folder in DETAIL_FOLDERS:
        for file in sorted((source / folder).glob("*.csv")):
            if file.name.startswith(OLD_ENTITY):
                _clone_detail_file(file, out / folder / file.name.replace(OLD_ENTITY, NEW_ENTITY))
            else:
                _link(file, out / folder / file.name)
    for folder in ("remittance_advices", "pdfs", "bank_statements"):
        _link(source / folder, out / folder)
    _masters_final(out)
    return out

"""Learn how bank codes map to categories from a labelled phase: `python -m closebooks.tools.learn_categories`.

Output: bank, bank_code, bank_subcode, direction, label, count, where label is a category or ITEM (the line settles
items). Only counts of code combinations; no row of the dataset is kept. Direction is credit or debit.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from ..load import load_table
from ..paths import CATEGORY_CODES, phase_dir

KEYS = ["bank", "bank_code", "bank_subcode", "direction", "label"]


def learn(txns: pl.DataFrame, golden: pl.DataFrame, before: str | None = None) -> pl.DataFrame:
    """Lines booked before `before` (ISO date) count; the rest are held out to validate the table."""
    if before:
        txns = txns.filter(pl.col("booking_date") < before)
    labels = golden.group_by("bank_txn_id").agg(
        pl.when(pl.col("item_id").is_not_null().any()).then(pl.lit("ITEM")).otherwise(pl.col("category").first())
        .alias("label"))
    return (
        txns.join(labels, on="bank_txn_id")
        .with_columns(
            pl.col("bank_code").fill_null(""), pl.col("bank_subcode").fill_null(""),
            pl.when(pl.col("amount").cast(pl.Float64) > 0).then(pl.lit("credit")).otherwise(pl.lit("debit"))
            .alias("direction"))
        .group_by(KEYS).len(name="count").sort(KEYS)
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="learn_categories")
    parser.add_argument("--phase", default="train")
    parser.add_argument("--before", help="only lines booked before this date (ISO)")
    parser.add_argument("--out", default=str(CATEGORY_CODES))
    args = parser.parse_args(argv)
    folder = phase_dir(args.phase)
    table = learn(load_table(folder / "bank_transactions.csv.gz"), load_table(folder / "golden_allocations.csv.gz"),
                  args.before)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    table.write_csv(args.out)
    print(f"{table.height} rows, {table['count'].sum()} lines -> {args.out}")


if __name__ == "__main__":
    main()

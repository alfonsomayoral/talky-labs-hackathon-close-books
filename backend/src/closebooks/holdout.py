"""db/holdout/: TRAIN cut at a date with the shape of FINAL, and db/holdout-drift/ with drift applied (PLAN §4)."""
from __future__ import annotations

import polars as pl

STILL_OPEN_AFTER = ("PARTIAL", "SHORT_DISPUTE", "RETURNED")


def open_items_at(items: pl.DataFrame, golden: pl.DataFrame, cut: str, unknown_before: str) -> pl.DataFrame:
    """Balance at the cut, from the golden.

    total - amounts, RETURNED add back, DUPLICATE_PAYMENT don't count; a RETURNED of a payment made before the data
    starts must not push it above the total. An item whose last row leaves nothing open (POLICIES §3), or whose
    advance covers the rest, is closed even if older payments are unknown. Items issued before unknown_before and
    never allocated have no known state (ANALYSIS §2): excluded.
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

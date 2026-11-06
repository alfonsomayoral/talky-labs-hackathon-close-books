"""Why each bank line is wrong, by segment: what a rule author reads before touching a rule (PLAN §10)."""
from __future__ import annotations

from pathlib import Path

import polars as pl

from .load import load_table
from .paths import phase_dir

_CAUSES = ("missing_item", "extra_item", "wrong_amount", "wrong_exception", "wrong_category", "forced", "not_matched")


def _cents(column: str) -> pl.Expr:
    return (pl.col(column).cast(pl.Float64) * 100).round().cast(pl.Int64)


def load_golden_rows(phase: str) -> pl.DataFrame:
    return load_table(phase_dir(phase) / "golden_allocations.csv.gz").select(
        "bank_txn_id", "item_id", _cents("amount").alias("amount_cents"), "category",
        pl.col("exception").fill_null(""), "segment")


def load_submission_rows(run: Path) -> pl.DataFrame:
    rows = load_table(run / "submission.csv.gz").select(
        "bank_txn_id", "item_id", _cents("amount").alias("amount_cents"), "category",
        pl.col("exception").fill_null(""))
    explanations = pl.read_ndjson(run / "explanations.jsonl.gz", schema={"rule": pl.String})
    return rows.with_columns(explanations["rule"])


def classify(golden: pl.DataFrame, submitted: pl.DataFrame) -> pl.DataFrame:
    """One row per wrong bank line, with the first cause that applies. Tolerance as in the official scorer."""
    pairs = golden.filter(pl.col("item_id").is_not_null()).join(
        submitted.filter(pl.col("item_id").is_not_null()), on=["bank_txn_id", "item_id"], how="full",
        coalesce=True, suffix="_sub")
    tolerance = pl.max_horizontal(pl.lit(1.0), pl.col("amount_cents").abs() * 0.005)
    per_txn = pairs.group_by("bank_txn_id").agg(
        pl.col("amount_cents").is_null().any().alias("extra"),
        pl.col("amount_cents_sub").is_null().any().alias("missing"),
        ((pl.col("amount_cents") - pl.col("amount_cents_sub")).abs() > tolerance).any().alias("amount"),
        (pl.col("exception") != pl.col("exception_sub")).any().alias("exception"),
        pl.col("amount_cents").is_not_null().sum().alias("golden_pairs"),
        pl.col("amount_cents_sub").is_not_null().sum().alias("sub_pairs"),
    )
    no_item_g = golden.filter(pl.col("item_id").is_null()).select(
        "bank_txn_id", "category", pl.col("exception").alias("exc_g"))
    no_item_s = submitted.filter(pl.col("item_id").is_null()).select(
        "bank_txn_id", pl.col("category").alias("category_sub"), pl.col("exception").alias("exception_sub"))
    segments = golden.group_by("bank_txn_id").agg(pl.col("segment").first())
    rules = submitted.group_by("bank_txn_id").agg(pl.col("rule").first())
    joined = (
        segments.join(per_txn, on="bank_txn_id", how="left")
        .join(no_item_g, on="bank_txn_id", how="left")
        .join(no_item_s, on="bank_txn_id", how="left")
        .join(rules, on="bank_txn_id", how="left")
    )
    has_gold = pl.col("golden_pairs").fill_null(0) > 0
    has_sub = pl.col("sub_pairs").fill_null(0) > 0
    bad_no_item = (pl.col("category") != pl.col("category_sub")) | (pl.col("exc_g") != pl.col("exception_sub"))
    cause = (
        pl.when(has_gold & ~has_sub).then(pl.lit("not_matched"))
        .when(~has_gold & has_sub).then(pl.lit("forced"))
        .when(pl.col("missing").fill_null(False)).then(pl.lit("missing_item"))
        .when(pl.col("extra").fill_null(False)).then(pl.lit("extra_item"))
        .when(pl.col("amount").fill_null(False)).then(pl.lit("wrong_amount"))
        .when(pl.col("exception").fill_null(False)).then(pl.lit("wrong_exception"))
        .when(~has_gold & bad_no_item.fill_null(False)).then(pl.lit("wrong_category"))
    )
    return joined.with_columns(cause.alias("cause")).filter(pl.col("cause").is_not_null()).select(
        "bank_txn_id", "segment", "cause", "rule").sort("bank_txn_id")


def exception_matrix(golden: pl.DataFrame, submitted: pl.DataFrame) -> pl.DataFrame:
    """Per exception class: golden rows, tp, fn, fp and the points of the 20 macro-F1 lost (2 per class of 10)."""
    keys = ["bank_txn_id", "item_id"]
    g = golden.filter(pl.col("exception") != "").select(*keys, pl.col("exception").alias("g"))
    s = submitted.filter(pl.col("exception") != "").select(*keys, pl.col("exception").alias("s"))
    joined = g.join(s, on=keys, how="full", coalesce=True, nulls_equal=True)
    classes = sorted(set(g["g"].to_list()) | set(s["s"].to_list()))
    n_golden = g["g"].n_unique() or 1
    rows = []
    for name in classes:
        tp = joined.filter((pl.col("g") == name) & (pl.col("s") == name)).height
        n_g = g.filter(pl.col("g") == name).height
        n_s = s.filter(pl.col("s") == name).height
        f1 = 2 * tp / (n_g + n_s) if n_g + n_s else 0.0
        rows.append({"exception": name, "golden": n_g, "tp": tp, "fn": n_g - tp, "fp": n_s - tp, "f1": round(f1, 4),
                     "points_lost": round((1 - f1) * 20 / n_golden, 3)})
    return pl.DataFrame(rows)


def report(run: Path, phase: str, segment: str | None = None, examples: int = 20) -> str:
    golden = load_golden_rows(phase)
    submitted = load_submission_rows(run)
    wrong = classify(golden, submitted)
    if segment:
        wrong = wrong.filter(pl.col("segment") == segment)
    pivot = wrong.group_by("segment", "cause", "rule").len().sort("len", descending=True)
    lines = [f"wrong lines: {wrong.height}", "", "segment, cause, rule, lines"]
    lines += [f"{a:32} {b:16} {c or '-':26} {n:>8}" for a, b, c, n in pivot.head(60).iter_rows()]
    lines += ["", "exception, golden, tp, fn, fp, f1, points_lost"]
    lines += ["  ".join(str(v) for v in row) for row in exception_matrix(golden, submitted).iter_rows()]
    if segment:
        lines += ["", "examples"]
        for cause in _CAUSES:
            ids = wrong.filter(pl.col("cause") == cause)["bank_txn_id"].head(examples).to_list()
            if ids:
                lines.append(f"{cause}: {' '.join(ids)}")
    return "\n".join(lines)

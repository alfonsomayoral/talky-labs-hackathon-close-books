from __future__ import annotations

import polars as pl
from conftest import require_phase

from closebooks.holdout import open_items_at
from closebooks.load import cancelled_item_ids, load_table, phase_items
from closebooks.paths import phase_dir


def test_opening_balances_are_a_pure_function_of_issues_and_golden():
    items = pl.DataFrame({
        "item_id": ["ARI-paid", "ARI-partial", "ARI-returned", "ARI-dup", "ARI-untouched-old", "ARI-new", "ARI-after"],
        "total_cents": [1000, 1000, 1000, 1000, 1000, 1000, 1000],
        "issue_date": ["2024-01-01"] * 4 + ["2021-03-01", "2024-06-01", "2025-02-01"],
    })
    golden = pl.DataFrame({
        "item_id": ["ARI-paid", "ARI-partial", "ARI-returned", "ARI-returned", "ARI-dup", "ARI-dup"],
        "amount_cents": [1000, 400, 1000, 1000, 1000, 1000],
        "exception": ["", "PARTIAL", "", "RETURNED", "", "DUPLICATE_PAYMENT"],
        "booking_date": ["2024-02-01"] * 6,
    })
    out = open_items_at(items, golden, cut="2024-12-31", unknown_before="2021-07-01")
    got = dict(zip(out["item_id"], out["open_cents"], strict=True))
    assert got == {"ARI-partial": 600, "ARI-returned": 1000, "ARI-new": 1000}


def test_return_of_a_payment_made_before_the_data_starts_never_exceeds_the_total():
    items = pl.DataFrame({"item_id": ["ARI-old"], "total_cents": [1000], "issue_date": ["2021-05-01"]})
    golden = pl.DataFrame({"item_id": ["ARI-old"], "amount_cents": [1000], "exception": ["RETURNED"],
                           "booking_date": ["2021-08-01"]})
    out = open_items_at(items, golden, cut="2024-12-31", unknown_before="2021-07-01")
    assert out["open_cents"].to_list() == [1000]


def test_old_item_first_settled_after_the_cut_is_open_at_the_cut():
    items = pl.DataFrame({"item_id": ["ARI-old"], "total_cents": [1000], "issue_date": ["2021-05-01"]})
    golden = pl.DataFrame({"item_id": ["ARI-old"], "amount_cents": [1000], "exception": [""],
                           "booking_date": ["2025-03-01"]})
    out = open_items_at(items, golden, cut="2024-12-31", unknown_before="2021-07-01")
    assert out["open_cents"].to_list() == [1000]


def test_a_row_without_shortfall_exception_clears_the_item_even_if_older_payments_are_unknown():
    # ARI-2021-0055063: instalments before TRAIN are not in the golden; the last one (empty exception) closes it.
    items = pl.DataFrame({"item_id": ["ARI-1"], "total_cents": [579806], "issue_date": ["2021-03-20"]})
    golden = pl.DataFrame({"item_id": ["ARI-1"] * 3, "amount_cents": [144951, 144951, 144953],
                           "exception": ["PARTIAL", "PARTIAL", ""],
                           "booking_date": ["2021-08-01", "2021-09-01", "2021-10-01"]})
    assert open_items_at(items, golden, cut="2024-12-31", unknown_before="2021-07-01").height == 0


def test_invoice_with_advance_deducted_is_closed_by_its_only_payment():
    items = pl.DataFrame({"item_id": ["ARI-1"], "total_cents": [1000], "issue_date": ["2024-01-01"]})
    golden = pl.DataFrame({"item_id": ["ARI-1"], "amount_cents": [700], "exception": ["PARTIAL"],
                           "booking_date": ["2024-03-01"], "segment": ["ar_advance_deduction"]})
    assert open_items_at(items, golden, cut="2024-12-31", unknown_before="2021-07-01").height == 0


def test_cancelled_invoice_and_its_credit_note_are_never_items_to_settle(sample):
    ids = cancelled_item_ids(sample.items)
    g = load_table(phase_dir("sample") / "golden_allocations.csv.gz")
    assert len(ids) > 0
    assert g.filter(pl.col("item_id").is_in(list(ids))).height == 0
    notes = sample.items.filter(pl.col("reason") == "Anulación de factura").row(0, named=True)
    assert notes["item_id"] in ids


def test_opening_balances_reproduce_the_official_file_of_live():
    require_phase("train")
    require_phase("live")
    items = phase_items("train")
    g = load_table(phase_dir("train") / "golden_allocations.csv.gz").filter(pl.col("item_id").is_not_null())
    bt = load_table(phase_dir("train") / "bank_transactions.csv.gz").select("bank_txn_id", "booking_date")
    golden = g.join(bt, on="bank_txn_id").with_columns(
        (pl.col("amount").cast(pl.Float64) * 100).round().cast(pl.Int64).alias("amount_cents"),
        pl.col("exception").fill_null(""))
    live_items = items.filter(~pl.col("item_id").is_in(list(cancelled_item_ids(items))))
    mine = open_items_at(live_items, golden, cut="2025-06-30", unknown_before="2021-07-01")
    official = load_table(phase_dir("live") / "open_items_at_start.csv.gz").with_columns(
        (pl.col("open_amount").cast(pl.Float64) * 100).round().cast(pl.Int64).alias("official"))
    joined = official.join(mine.select("item_id", "open_cents"), on="item_id", how="left")
    # About 3,960 items of 2021-03..06 are open in the official file with no trace in TRAIN: not reproducible.
    assert joined.filter(pl.col("open_cents").is_null()).height <= 4000
    assert joined.filter(pl.col("open_cents") != pl.col("official")).height <= 100
    assert mine.join(official, on="item_id", how="anti").height <= 500

from __future__ import annotations

import polars as pl
from conftest import require_phase

from closebooks.holdout import bank_to_camt, clone_entity, delayable_receipts, open_items_at
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


def test_n43_bank_moves_to_camt_from_a_date_and_keeps_its_code_in_the_subcode():
    txns = pl.DataFrame({
        "bank": ["RIBA", "RIBA", "OTHR"], "booking_date": ["2025-03-31", "2025-04-01", "2025-04-01"],
        "statement_format": ["n43", "n43", "mt940"], "bank_code": ["04", "04", "NTRF"],
        "bank_subcode": ["532", "532", None], "amount_cents": [100, -100, 100],
        "text": ["T1", "T2", "T3"], "remittance_info": [None, None, None],
    })
    out = bank_to_camt(txns, "RIBA", "2025-04-01")
    assert out["statement_format"].to_list() == ["n43", "camt053", "mt940"]
    assert out["bank_subcode"].to_list() == ["532", "04532", None]
    assert out["bank_code"].to_list() == ["04", "PMNT/ICDT/ESCT", "NTRF"]
    assert out["remittance_info"].to_list() == [None, "T2", None]


def test_new_entity_doubles_only_amounts_in_the_old_currency_and_renumbers_items():
    items = pl.DataFrame({
        "item_id": ["ARI-1", "ARI-2", "ARI-3"], "entity": ["MA01", "MA01", "ES01"], "currency": ["MAD", "EUR", "EUR"],
        "total_amount": ["10.50", "20.00", "30.00"], "document_number": ["FA210100025", "FA210100026", "FA210100027"],
        "customer_id": ["CMA01000300", "CMA01000301", "CES01000301"],
    })
    out = clone_entity(items, amount_cols=["total_amount"], number_cols=["document_number"])
    assert out["entity"].to_list() == ["ZA01", "ZA01", "ES01"]
    assert out["currency"].to_list() == ["ZAR", "EUR", "EUR"]
    assert out["total_amount"].to_list() == ["21.00", "20.00", "30.00"]
    assert out["document_number"].to_list() == ["KWI210100025", "KWI210100026", "FA210100027"]
    assert out["customer_id"].to_list() == ["CZA01000300", "CZA01000301", "CES01000301"]


def test_built_holdout_has_the_shape_of_final():
    require_phase("holdout")
    txns = load_table(phase_dir("holdout") / "bank_transactions.csv.gz")
    assert txns["booking_date"].min() >= "2025-01-01"
    assert txns["booking_date"].max() == "2025-06-30"
    train = load_table(phase_dir("train") / "bank_transactions.csv.gz")
    assert txns.height == train.filter(pl.col("booking_date") >= "2025-01-01").height
    opening = load_table(phase_dir("holdout") / "open_items_at_start.csv.gz")
    assert set(opening.columns) == {"item_id", "item_type", "entity", "party_id", "document_number", "issue_date",
                                    "due_date", "currency", "total_amount", "open_amount"}
    assert (opening["open_amount"].cast(pl.Float64) > 0).all()
    g = load_table(phase_dir("holdout") / "golden_allocations.csv.gz")
    assert set(g["bank_txn_id"]) == set(txns["bank_txn_id"])
    assert (phase_dir("holdout") / "payment_runs" / "ES01_202501_0.csv").exists()
    assert not (phase_dir("holdout") / "payment_runs" / "ES01_202412_0.csv").exists()


def test_built_drift_holdout_is_consistent_and_keeps_new_entity_out_of_the_package_masters():
    require_phase("holdout-drift")
    folder = phase_dir("holdout-drift")
    txns = load_table(folder / "bank_transactions.csv.gz")
    assert "MA01" not in set(txns["entity"])
    assert txns.filter(pl.col("entity") == "ZA01", pl.col("currency") == "ZAR").height > 0
    assert (folder / "masters_final" / "entities.csv").exists()
    masters = load_table(folder / "masters_final" / "entities.csv")
    assert "ZA01" in set(masters["entity"])
    golden = load_table(folder / "golden_allocations.csv.gz").select("bank_txn_id", "item_id", "amount", "category",
                                                                     "exception")
    assert set(golden["bank_txn_id"]) == set(txns["bank_txn_id"])
    items = phase_items("holdout-drift")
    missing = golden.filter(pl.col("item_id").is_not_null()).join(items, on="item_id", how="anti").select("item_id")
    # Items closed before the cut and paid again (duplicates, returns) are in no item table of the phase.
    assert missing.n_unique() / golden["item_id"].n_unique() < 0.02


def test_only_payments_of_items_with_no_other_movement_are_delayed():
    # A delayed original would land after its own duplicate and turn the labels upside down.
    golden = pl.DataFrame({
        "bank_txn_id": ["BT-1", "BT-2", "BT-3", "BT-4"], "item_id": ["I1", "I2", "I2", None],
        "segment": ["ar_1to1", "ar_1to1", "ar_duplicate_payment", "ar_1to1"], "exception": [None, None, "X", None]})
    assert sorted(delayable_receipts(golden)["bank_txn_id"].to_list()) == ["BT-1"]

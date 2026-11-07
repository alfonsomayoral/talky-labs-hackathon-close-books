from __future__ import annotations

from functools import partial

import polars as pl
import pytest
from conftest import require_phase

from closebooks import holdout, paths
from closebooks.cli import main
from closebooks.holdout import (
    _fresh,
    _link_indexed,
    _link_months,
    bank_to_camt,
    clone_entity,
    delayable_receipts,
    open_items_at,
    period_dest,
)
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


def test_a_debit_keeps_its_cents_when_the_drift_doubles_its_currency():
    # BT-2025-0001782: -9761.77 MAD came out as -19524.46 ZAR, and the 92 cents looked like an overpayment.
    from closebooks.holdout import _text_amount

    frame = pl.DataFrame({"cents": [-1952354, 1952354]})
    assert frame.select(_text_amount(pl.col("cents")).alias("text"))["text"].to_list() == ["-19523.54", "19523.54"]


def test_a_build_never_empties_a_folder_that_is_not_a_holdout(tmp_path):
    for name in ("train", "live", "final", "sample", "bankrec-docs-and-masters"):
        real = tmp_path / name
        real.mkdir()
        (real / "bank_transactions.csv.gz").write_text("real data")
        with pytest.raises(ValueError, match=name):
            _fresh(real)
        assert (real / "bank_transactions.csv.gz").read_text() == "real data"


def test_a_holdout_is_rebuilt_empty(tmp_path):
    for name in ("holdout", "holdout-drift"):
        old = tmp_path / name
        old.mkdir()
        (old / "stale.csv").write_text("x")
        assert list(_fresh(old).iterdir()) == []


def test_a_period_goes_only_to_a_new_holdout_folder(tmp_path):
    assert period_dest("holdout-2024h2", tmp_path) == tmp_path / "holdout-2024h2"


def test_only_the_files_of_the_months_of_the_period_are_linked(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    for name in ("ES01_202406_0.csv", "ES01_202407_0.csv", "ES01_202412_1.csv", "ES01_202501_0.csv"):
        (source / name).write_text("x")
    _link_months(source, target, "2024-07-01", "2024-12-31")
    assert sorted(f.name for f in target.iterdir()) == ["ES01_202407_0.csv", "ES01_202412_1.csv"]


def test_only_the_documents_dated_in_the_period_are_linked(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    (source / "index.csv").write_text("file,received_date\na.pdf,2024-06-30\nb.pdf,2024-07-01\nc.pdf,2025-01-01\n")
    for name in ("a.pdf", "b.pdf", "c.pdf"):
        (source / name).write_text("x")
    _link_indexed(source, target, "received_date", "2024-07-01", "2024-12-31")
    assert sorted(f.name for f in target.iterdir()) == ["b.pdf", "index.csv"]
    assert load_table(target / "index.csv")["file"].to_list() == ["b.pdf"]


@pytest.mark.parametrize("name", [
    "train", "live", "final", "holdout", "holdoutx", "holdout-drift",
    "../train", "../holdout-x", "holdout-x/../../train", "holdout-x/y", "holdout-x/", "/tmp/holdout-x",
])
def test_a_period_refuses_the_name_even_when_no_such_folder_exists_yet(tmp_path, name):
    db = tmp_path / "db"
    db.mkdir()
    with pytest.raises(ValueError, match="a period goes to"):
        period_dest(name, db)


PERIOD = ["--start", "2024-07-01", "--end", "2024-12-31"]


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A TRAIN of a few rows in an entity and a currency no code knows, and the CLI pointed at it, never at db/."""
    root = tmp_path / "db"
    train = root / "train"
    train.mkdir(parents=True)
    for table, rows in {
        "bank_transactions": {"bank_txn_id": ["T0", "T1", "T2", "T3"],
                              "booking_date": ["2024-06-20", "2024-08-10", "2024-10-10", "2025-03-10"]},
        "golden_allocations": {"bank_txn_id": ["T1", "T2", "T3"], "item_id": ["A", "B", "C"],
                               "amount": ["100.00", "50.00", "70.00"], "exception": [None, None, None],
                               "segment": ["ar_1to1", "ar_1to1", "ar_1to1"]},
        "ar_invoices": {"item_id": ["A", "B", "C", "X"], "entity": ["QQ01"] * 4, "customer_id": ["C1"] * 4,
                        "customer_name": ["n"] * 4, "document_number": ["DA", "DB", "DC", "DX"],
                        "issue_date": ["2024-03-01", "2024-09-01", "2025-02-01", "2024-03-02"],
                        "due_date": ["2024-04-01", "2024-10-01", "2025-03-01", "2024-04-02"], "currency": ["QQQ"] * 4,
                        "total_amount": ["100.00", "50.00", "70.00", "10.00"], "payment_terms": ["30"] * 4,
                        "customer_po": [None] * 4, "payment_method": ["SEPA"] * 4},
        "ap_invoices": {"item_id": ["P"], "entity": ["QQ01"], "supplier_id": ["S1"], "supplier_name": ["s"],
                        "supplier_invoice_number": ["DP"], "issue_date": ["2024-11-01"], "due_date": ["2024-12-01"],
                        "currency": ["QQQ"], "total_amount": ["20.00"], "payment_terms": ["30"], "our_po": [None],
                        "payment_method": ["SEPA"]},
        "credit_notes": {"item_id": ["ARC1"], "entity": ["QQ01"], "party_id": ["C1"], "party_name": ["n"],
                         "document_number": ["DN"], "issue_date": ["2024-03-03"], "currency": ["QQQ"],
                         "total_amount": ["-10.00"], "related_document": ["DX"], "reason": ["Anulación de factura"]},
    }.items():
        holdout._write_gz(pl.DataFrame(rows, schema={c: pl.String for c in rows}), train / f"{table}.csv.gz")
    for folder, column in (("remittance_advices", "received_date"), ("pdfs", "document_date")):
        (train / folder).mkdir()
        (train / folder / "index.csv").write_text(f"file,{column}\n")
    monkeypatch.setattr(paths, "DB", root)
    monkeypatch.setattr(paths, "PKG", root / "package")
    monkeypatch.setattr(holdout, "DB", root)
    monkeypatch.setattr(holdout, "period_dest", partial(holdout.period_dest, db=root))
    return root


def test_the_cli_builds_the_period_it_is_given_from_train(db):
    assert main(["holdout", "build", *PERIOD, "--name", "holdout-2024h2"]) == 0

    out = paths.phase_dir("holdout-2024h2")
    assert load_table(out / "bank_transactions.csv.gz")["bank_txn_id"].to_list() == ["T1", "T2"]
    assert load_table(out / "golden_allocations.csv.gz")["item_id"].to_list() == ["A", "B"]
    assert load_table(out / "ar_invoices.csv.gz")["item_id"].to_list() == ["B"]
    opening = load_table(out / "open_items_at_start.csv.gz")
    assert opening.select("item_id", "entity", "currency", "open_amount").rows() == [("A", "QQ01", "QQQ", "100.00")]


def test_the_cli_refuses_a_period_over_a_phase_and_leaves_it_as_it_was(db):
    before = (db / "train" / "bank_transactions.csv.gz").read_bytes()
    with pytest.raises(ValueError, match="a period goes to"):
        main(["holdout", "build", *PERIOD, "--name", "train"])
    assert (db / "train" / "bank_transactions.csv.gz").read_bytes() == before


def test_the_cli_refuses_a_period_over_a_holdout_folder_that_already_exists(db):
    (db / "holdout-2024h2").mkdir()
    (db / "holdout-2024h2" / "kept.csv").write_text("x")
    with pytest.raises(ValueError, match="exists"):
        main(["holdout", "build", *PERIOD, "--name", "holdout-2024h2"])
    assert (db / "holdout-2024h2" / "kept.csv").read_text() == "x"


@pytest.mark.parametrize("flags", [
    PERIOD,  # without --name it would empty db/holdout and rebuild it with the default dates
    ["--name", "holdout-2024h2"],
    ["--name", "holdout-2024h2", "--start", "2024-07-01"],
    ["--drift", *PERIOD, "--name", "holdout-2024h2"],
])
def test_the_cli_refuses_a_half_given_period_before_touching_anything(db, flags):
    (db / "holdout").mkdir()
    (db / "holdout" / "kept.csv").write_text("x")
    with pytest.raises(SystemExit, match="--name"):
        main(["holdout", "build", *flags])
    assert (db / "holdout" / "kept.csv").read_text() == "x"
    assert not (db / "holdout-2024h2").exists()


def test_the_normal_build_still_rebuilds_db_holdout_with_its_own_period(db):
    (db / "holdout").mkdir()
    (db / "holdout" / "stale.csv").write_text("x")
    assert main(["holdout", "build"]) == 0
    assert not (db / "holdout" / "stale.csv").exists()
    assert load_table(db / "holdout" / "bank_transactions.csv.gz")["bank_txn_id"].to_list() == ["T3"]


def test_the_drift_build_is_not_taken_for_a_period(db):
    with pytest.raises(FileNotFoundError, match="holdout"):  # it reads db/holdout, which this db does not have
        main(["holdout", "build", "--drift"])

from __future__ import annotations

import os
import subprocess
import sys
from types import SimpleNamespace

import polars as pl
import pytest

from closebooks.load import load_detail, load_masters, to_cents
from closebooks.paths import masters_dir, phase_dir


def test_amounts_are_exact_integer_cents():
    # 1403.94 * 100 is 140393.99999... in floats: truncating would lose a cent.
    assert to_cents(pl.Series(["1403.94", "-2312384.15", "0.29", None])).to_list() == [140394, -231238415, 29, None]


def test_bank_line_keeps_sign_and_currency(sample):
    row = sample.txns.filter(pl.col("bank_txn_id") == "BT-2025-0162712").row(0, named=True)
    assert row["amount_cents"] == -231238415
    assert row["currency"] == "EUR"
    assert row["counterparty_name"] is None


def test_bank_line_in_foreign_currency_gets_eur_amount_at_last_available_rate(sample):
    # Every line of a non-EUR account has its EUR equivalent; EUR lines keep their amount.
    eur = sample.txns.filter(pl.col("currency") == "EUR").select(pl.col("amount_eur_cents") == pl.col("amount_cents"))
    assert eur.to_series().all()
    usd = sample.txns.filter(pl.col("currency") == "USD")
    assert usd["amount_eur_cents"].null_count() == 0
    ratio = (usd["amount_eur_cents"].abs() / usd["amount_cents"].abs()).median()
    assert 0.8 < ratio < 1.0


def test_items_of_all_tables_share_one_shape(sample):
    by_id = {r["item_id"]: r for r in sample.items.filter(
        pl.col("item_id").is_in(["ARI-2025-1237464"])).iter_rows(named=True)}
    item = by_id["ARI-2025-1237464"]
    assert item["item_type"] == "ARI"
    assert item["total_cents"] == 140394
    assert item["open_cents"] == 140394
    assert set(sample.items["item_type"].unique()) == {"ARI", "ARC", "API", "APC"}


def test_supplier_invoice_number_is_the_document_number(sample):
    row = sample.items.filter(pl.col("item_type") == "API").row(0, named=True)
    assert row["document_number"]
    assert row["party_id"].startswith("S")


def test_open_item_with_partial_balance_starts_at_its_open_amount(live):
    partial = live.open_at_start.filter(pl.col("open_cents") < pl.col("total_cents")).row(0, named=True)
    item = live.items.filter(pl.col("item_id") == partial["item_id"]).row(0, named=True)
    assert item["open_cents"] == partial["open_cents"]
    assert item["total_cents"] == partial["total_cents"]


def test_every_item_of_live_is_issued_in_the_phase_or_open_at_start(live):
    assert live.items["item_id"].n_unique() == live.items.height
    in_phase_or_open = live.items.filter(pl.col("issue_date") >= "2025-07-01").height + live.open_at_start.height
    assert in_phase_or_open == 487243 + 199414 + 19500 + 325419


def test_masters_final_win_over_the_package_masters(tmp_path):
    phase = tmp_path / "final"
    (phase / "masters_final").mkdir(parents=True)
    assert masters_dir(phase) == phase / "masters_final"
    (phase / "masters_final" / "entities.csv").write_text("entity,legal_name\nZA01,Umvoti Pools\n")
    with pytest.raises(FileNotFoundError):
        load_masters(phase)  # the other masters are missing: fails loud instead of mixing folders silently


def test_item_carried_over_from_the_previous_phase_keeps_its_name_and_terms(live):
    carried = live.open_at_start.join(pl.read_csv(
        phase_dir("live") / "ar_invoices.csv.gz", infer_schema_length=0).select("item_id"), on="item_id", how="anti")
    row = live.items.filter(pl.col("item_id").is_in(carried.filter(pl.col("item_type") == "ARI")["item_id"].head(50)
                                                    .to_list()))
    assert row["party_name"].null_count() == 0
    assert row["payment_terms"].null_count() == 0


def test_item_closed_in_the_previous_phase_exists_with_nothing_open(live):
    closed = live.items.filter(pl.col("issue_date") < "2025-07-01", pl.col("open_cents") == 0)
    assert closed.height > 100_000
    assert closed["item_id"].n_unique() == closed.height


def test_detail_file_of_the_previous_month_is_read_but_not_older_ones(tmp_path):
    (tmp_path / "train" / "payment_runs").mkdir(parents=True)
    (tmp_path / "live" / "payment_runs").mkdir(parents=True)
    for name, folder in (("ES01_202506_0.csv", "train"), ("ES01_202412_0.csv", "train"), ("ES01_202507_0.csv", "live")):
        (tmp_path / folder / "payment_runs" / name).write_text(f"run_id\n{name}\n")
    phase = SimpleNamespace(dir=tmp_path / "live", prior=[tmp_path / "train"], start="2025-07-01")
    assert sorted(load_detail(phase, "payment_runs")["run_id"]) == ["ES01_202506_0.csv", "ES01_202507_0.csv"]


def test_polars_returns_freed_memory_to_the_system_unless_told_otherwise():
    code = "import os, closebooks, polars; print(os.environ['_RJEM_MALLOC_CONF'])"
    env = {k: v for k, v in os.environ.items() if k != "_RJEM_MALLOC_CONF"}
    default = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    assert default.stdout.strip().endswith("dirty_decay_ms:0,muzzy_decay_ms:0")
    chosen = subprocess.run([sys.executable, "-c", code], env={**env, "_RJEM_MALLOC_CONF": "narenas:1"},
                            capture_output=True, text=True, check=True)
    assert "dirty_decay_ms:0" not in chosen.stdout


def test_a_bank_line_with_no_rate_stays_at_one_and_says_which_currency(capsys):
    from closebooks.load import _with_eur

    lines = pl.DataFrame({"booking_date": ["2025-01-02"] * 3, "currency": ["HUF", "HUF", "USD"],
                          "amount_cents": [500, 300, 110]})
    rates = pl.DataFrame({"date": ["2025-01-01"], "currency": ["USD"], "units_per_eur": ["1.10"]})
    assert sorted(_with_eur(lines, rates)["amount_eur_cents"].to_list()) == [100, 300, 500]
    assert "HUF" in capsys.readouterr().err


def test_every_rate_found_says_nothing(capsys):
    from closebooks.load import _with_eur

    lines = pl.DataFrame({"booking_date": ["2025-01-02"] * 2, "currency": ["EUR", "USD"], "amount_cents": [100, 110]})
    rates = pl.DataFrame({"date": ["2025-01-01"], "currency": ["USD"], "units_per_eur": ["1.10"]})
    _with_eur(lines, rates)
    assert capsys.readouterr().err == ""

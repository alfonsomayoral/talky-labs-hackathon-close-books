from __future__ import annotations

import polars as pl
import pytest

from closebooks.load import load_masters, to_cents
from closebooks.paths import masters_dir


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
    assert live.items.height == 487243 + 199414 + 19500 + 325419


def test_masters_final_win_over_the_package_masters(tmp_path):
    phase = tmp_path / "final"
    (phase / "masters_final").mkdir(parents=True)
    assert masters_dir(phase) == phase / "masters_final"
    (phase / "masters_final" / "entities.csv").write_text("entity,legal_name\nZA01,Umvoti Pools\n")
    with pytest.raises(FileNotFoundError):
        load_masters(phase)  # the other masters are missing: fails loud instead of mixing folders silently

from __future__ import annotations

import gzip
import importlib.util
from pathlib import Path

import polars as pl
import pytest

from closebooks import paths
from closebooks.load import MASTER_FILES

SCRIPT = Path(__file__).parents[2] / "scripts" / "final_check.py"


@pytest.fixture
def final_check(monkeypatch):
    spec = importlib.util.spec_from_file_location("final_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "validate_file", lambda *_: {"ok": True, "errors": []})
    return module


@pytest.fixture
def phase(tmp_path, monkeypatch):
    """A phase like db/final: no masters/, so what masters_final replaces is in the package."""
    monkeypatch.setattr(paths, "PKG", tmp_path / "pkg")
    masters = tmp_path / "pkg" / "masters"
    masters.mkdir(parents=True)
    for name in MASTER_FILES:
        (masters / f"{name}.csv").write_text("currency\nEUR\nUSD\nZAR\n")
    folder = tmp_path / "final"
    (folder / "masters_final").mkdir(parents=True)
    with gzip.open(folder / "bank_transactions.csv.gz", "wt") as handle:
        handle.write("currency,orig_currency\nEUR,\n")
    return folder


def _masters_row(final_check, tmp_path, phase) -> tuple[str, bool, str]:
    """_hard_checks over a one-line run where every other check passes, so only the masters can turn it red."""
    bank = pl.DataFrame({"bank_txn_id": ["T1"], "entity": ["E1"], "bank": ["BK"]})
    profile = {"meta": {"dataDir": str(phase), "csvBytes": 1000}, "bank_ids": bank["bank_txn_id"], "bank": bank,
               "row_ids": bank["bank_txn_id"],
               "rule_rows": pl.DataFrame({"bankTxnId": ["T1"], "rule": ["RULE"], "category": ["X"]})}
    checks = final_check._hard_checks(tmp_path / "run", profile)
    row = next(c for c in checks if "masters_final" in c[0])
    assert [c[0] for c in checks if not c[1] and c is not row] == []
    return row


def test_final_check_goes_red_on_a_masters_final_file_shorter_than_the_package_one(final_check, tmp_path, phase):
    (phase / "masters_final" / "customers.csv").write_text("currency\nZAR\n")
    _, ok, detail = _masters_row(final_check, tmp_path, phase)
    assert ok is False
    assert "customers.csv" in detail and "1" in detail and "3" in detail


def test_final_check_stays_green_on_a_complete_masters_final_file(final_check, tmp_path, phase):
    (phase / "masters_final" / "customers.csv").write_text("currency\nEUR\nUSD\nZAR\n")
    _, ok, detail = _masters_row(final_check, tmp_path, phase)
    assert ok is True
    assert detail == "ok"

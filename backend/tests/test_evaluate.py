from __future__ import annotations

import gzip

import polars as pl

from closebooks.evaluate import score_file, segment_changes, validate_file
from closebooks.paths import phase_dir


def golden_as_submission(sample, path):
    g = pl.read_csv(phase_dir("sample") / "golden_allocations.csv.gz", infer_schema_length=0)
    g.select("bank_txn_id", "item_id", "amount", "category", "exception").write_csv(path)


def test_the_golden_scores_100_and_a_missing_line_does_not(tmp_path, sample):
    full = tmp_path / "full.csv"
    golden_as_submission(sample, full)
    assert score_file(full, "sample")["score"] == 100.0

    lines = full.read_text().splitlines()
    first_txn = lines[1].split(",")[0]
    cut = tmp_path / "cut.csv"
    cut.write_text("\n".join(x for x in lines if not x.startswith(first_txn)) + "\n")
    assert score_file(cut, "sample")["score"] < 100.0


def test_local_scoring_relaxes_limits_but_validation_keeps_the_official_60_mb(tmp_path, sample):
    big = tmp_path / "big.csv.gz"
    txn = sample.txns["bank_txn_id"][0]
    payload = "bank_txn_id,item_id,amount,category,exception\n" + (f"{txn},,,UNIDENTIFIED,UNIDENTIFIED\n" * 1)
    padding = "\n" * (61 * 1024 * 1024)
    big.write_bytes(gzip.compress((payload + padding).encode()))
    assert score_file(big, "sample")["ok"]
    report = validate_file(big, sample)
    assert not report["ok"]
    assert "60 MB" in report["errors"][0]["message"] or "80 MB" in report["errors"][0]["message"]


def test_validation_rejects_an_unknown_line(tmp_path, sample):
    bad = tmp_path / "bad.csv"
    bad.write_text("bank_txn_id,item_id,amount,category,exception\nBT-1999-0000000,,,BANK_FEES,\n")
    report = validate_file(bad, sample)
    assert not report["ok"]
    assert "BT-1999-0000000" in report["errors"][0]["message"]


def test_segment_comparison_lists_drops_first():
    base = {"up": {"n": 5, "accuracy": 0.1}, "down": {"n": 3, "accuracy": 0.9}}
    now = {"up": {"n": 5, "accuracy": 0.8}, "down": {"n": 3, "accuracy": 0.5}}
    assert segment_changes(base, now)[0] == ("down", 3, 0.9, 0.5)

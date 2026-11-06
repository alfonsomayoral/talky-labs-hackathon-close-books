from __future__ import annotations

import gzip

import polars as pl

from closebooks.evaluate import validate_file
from closebooks.pipeline import run_pipeline


def test_sample_run_covers_every_line_and_is_byte_identical(tmp_path, sample):
    a = run_pipeline("sample", out=tmp_path / "a", score=False)
    b = run_pipeline("sample", out=tmp_path / "b", score=False)
    assert (a / "submission.csv.gz").read_bytes() == (b / "submission.csv.gz").read_bytes()

    text = gzip.decompress((a / "submission.csv.gz").read_bytes()).decode()
    assert text.startswith("bank_txn_id,item_id,amount,category,exception\n")
    assert '"' not in text
    rows = pl.read_csv(a / "submission.csv.gz", infer_schema_length=0)
    assert set(rows["bank_txn_id"]) == set(sample.txns["bank_txn_id"])

    report = validate_file(a / "submission.csv.gz", sample)
    assert report["ok"], report["errors"]


def test_every_contract_file_is_written_with_one_explanation_per_row(tmp_path):
    run = run_pipeline("sample", out=tmp_path / "r", score=False)
    for name in ("submission.csv.gz", "explanations.jsonl.gz", "cases.jsonl.gz", "facts/documents.parquet",
                 "facts/parties.parquet", "state/open_items.parquet", "questions.jsonl", "drafts.jsonl", "run.json"):
        assert (run / name).exists(), name
    csv_rows = gzip.decompress((run / "submission.csv.gz").read_bytes()).decode().splitlines()[1:]
    expl = gzip.decompress((run / "explanations.jsonl.gz").read_bytes()).decode().splitlines()
    assert len(csv_rows) == len(expl)
    assert csv_rows[0].split(",")[0] in expl[0]


def test_run_json_measures_the_uncompressed_csv(tmp_path):
    import json

    run = run_pipeline("sample", out=tmp_path / "r", score=False)
    meta = json.loads((run / "run.json").read_text())
    assert meta["csvBytes"] == len(gzip.decompress((run / "submission.csv.gz").read_bytes()))
    assert meta["txns"] == 8499
    assert sum(meta["byRule"].values()) == meta["rows"]

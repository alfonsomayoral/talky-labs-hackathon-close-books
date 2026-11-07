from __future__ import annotations

import json

import pytest

from closebooks import pipeline
from closebooks.cli import main


def test_scored_run_does_not_load_reconciliation_data_in_the_scoring_process(tmp_path, monkeypatch, sample):
    def cannot_load_in_parent(*args, **kwargs):
        pytest.fail("reconciliation data must be released by exiting the worker before scoring")

    monkeypatch.setattr(pipeline, "load_phase", cannot_load_in_parent)
    run = pipeline.run_pipeline("sample", out=tmp_path / "isolated")
    meta = json.loads((run / "run.json").read_bytes())
    assert meta["score"]["ok"], meta["score"]["errors"]
    assert meta["score"]["metrics"]["txns_covered"] == sample.txns.height
    assert meta["score"]["metrics"]["rows"] == meta["rows"]
    assert meta["durationMs"] == sum(meta["stages"].values())


def test_cli_can_write_a_complete_run_without_loading_the_golden(tmp_path, monkeypatch, sample):
    def cannot_score(*args, **kwargs):
        pytest.fail("--no-score must not load the golden")

    monkeypatch.setattr(pipeline, "score_file", cannot_score)
    assert main(["run", "--phase", "sample", "--out", str(tmp_path), "--no-score"]) == 0
    meta = json.loads((tmp_path / "run.json").read_bytes())
    assert meta["txns"] == sample.txns.height
    assert meta["score"] is None and "score" not in meta["stages"]
    assert (tmp_path / "state" / "open_items.parquet").exists()

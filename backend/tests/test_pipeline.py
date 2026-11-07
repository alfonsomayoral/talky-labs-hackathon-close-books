from __future__ import annotations

import json

import pytest

from closebooks import pipeline
from closebooks.api.jobs import Job, Jobs
from closebooks.cli import main


def test_streaming_run_reports_resolve_even_though_the_submission_file_is_already_open(tmp_path):
    run = tmp_path / "streaming"
    run.mkdir()
    (run / "submission.csv.gz").write_bytes(b"partial gzip")
    (run / "progress.json").write_text(json.dumps({"stage": "resolve", "completedTxns": 5000,
                                                 "stages": {"load": 100, "rules": 300}}))
    jobs = Jobs(tmp_path)
    job = Job("streaming")
    job.status = "running"
    jobs.jobs[job.run_id] = job
    status = jobs.status("streaming")
    assert status["stage"] == "resolve"
    assert status["stages"] == {"load": 100, "rules": 300}


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

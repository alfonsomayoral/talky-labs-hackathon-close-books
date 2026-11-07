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


def test_every_contract_file_is_written_with_one_explanation_per_row(tmp_path, sample):
    run = run_pipeline("sample", out=tmp_path / "r", score=False)
    for name in ("submission.csv.gz", "explanations.jsonl.gz", "cases.jsonl.gz", "facts/documents.parquet",
                 "facts/parties.parquet", "state/open_items.parquet", "questions.jsonl", "drafts.jsonl", "run.json"):
        assert (run / name).exists(), name
    csv_rows = gzip.decompress((run / "submission.csv.gz").read_bytes()).decode().splitlines()[1:]
    expl = gzip.decompress((run / "explanations.jsonl.gz").read_bytes()).decode().splitlines()
    assert len(csv_rows) == len(expl)
    assert csv_rows[0].split(",")[0] in expl[0]


def test_run_json_measures_the_uncompressed_csv(tmp_path, sample):
    import json

    run = run_pipeline("sample", out=tmp_path / "r", score=False)
    meta = json.loads((run / "run.json").read_text())
    assert meta["csvBytes"] == len(gzip.decompress((run / "submission.csv.gz").read_bytes()))
    assert meta["txns"] == 8499
    assert sum(meta["byRule"].values()) == meta["rows"]


def test_open_items_hold_every_issued_item_but_not_those_closed_in_earlier_phases(tmp_path):
    import polars as pl

    from closebooks.load import Phase
    from closebooks.output import write_open_items
    from closebooks.state import OpenBalances

    cols = ["item_id", "item_type", "entity", "party_id", "party_name", "document_number", "issue_date", "due_date",
            "currency", "total_cents", "open_cents"]

    def item(item_id, open_cents, total=1000):
        return (item_id, "ARI", "E1", "C1", "n", item_id, "2025-07-01", "2025-08-01", "EUR", total, open_cents)

    items = pl.DataFrame([item("NEW-UNPAID", 1000), item("PAID", 1000), item("CARRIED", 400),
                          item("OLD-CLOSED", 0)], schema=cols + [], orient="row")
    for extra in ("payment_terms", "customer_po", "payment_method", "related_document", "reason"):
        items = items.with_columns(pl.lit(None, pl.String).alias(extra))
    opening = pl.DataFrame({"item_id": ["CARRIED"]})
    phase = Phase("x", tmp_path, {}, pl.DataFrame(), items, opening)
    balances = OpenBalances(dict(zip(items["item_id"], items["open_cents"], strict=True)))
    balances.apply("PAID", 1000, "", "BT-1", "2025-07-02")
    write_open_items(tmp_path, phase, balances)
    rows = {r["itemId"]: r for r in pl.read_parquet(tmp_path / "state" / "open_items.parquet").iter_rows(named=True)}
    assert set(rows) == {"NEW-UNPAID", "PAID", "CARRIED"}
    assert (rows["NEW-UNPAID"]["status"], rows["NEW-UNPAID"]["openAtEndCents"]) == ("open", 1000)
    assert rows["PAID"]["status"] == "cleared" and rows["CARRIED"]["openAtStartCents"] == 400

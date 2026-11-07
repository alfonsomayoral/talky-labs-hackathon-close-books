from __future__ import annotations

import gzip
import json
import tracemalloc
from itertools import repeat

import polars as pl
import pytest

from closebooks.evaluate import validate_file
from closebooks.model import Row
from closebooks.output import write_cases, write_explanations, write_jsonl, write_submission
from closebooks.pipeline import run_pipeline


@pytest.mark.parametrize("kind", ["explanations", "cases", "jsonl"])
def test_json_outputs_do_not_buffer_all_records_before_writing(tmp_path, kind):
    # A large reference is shared in the input: memory should depend on the write buffer, not the row count.
    source = {"kind": "pdf", "ref": "pdfs/ES01/factura.pdf", "label": "á" * 2048}
    row = Row("BT-1", "ARI-1", 1234, "EUR", None, None, "REF-TEXT", 1.0, sources=[source])
    record = {"caseId": "CASE-BT-1", "sources": [source]}
    count = 5000
    tracemalloc.start()
    try:
        if kind == "explanations":
            write_explanations(tmp_path, repeat(row, count))
            path = tmp_path / "explanations.jsonl.gz"
        elif kind == "cases":
            write_cases(tmp_path, repeat(record, count))
            path = tmp_path / "cases.jsonl.gz"
        else:
            path = tmp_path / "questions.jsonl"
            write_jsonl(path, repeat(record, count))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 4 * 1024 * 1024, f"writer buffered {peak / 1024**2:.1f} MiB for the full output"
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        first = json.loads(next(stream))
        assert first["sources"] == [source]
        assert sum(1 for _ in stream) + 1 == count


def test_submission_stream_counts_bytes_and_preserves_allocations_and_categories(tmp_path):
    rows = [Row("BT-1", "ARI-1", 1234, "EUR", None, "PARTIAL", "REF-TEXT", 1.0),
            Row("BT-1", "ARC-2", 500, "EUR", None, None, "REF-TEXT", 1.0),
            Row("BT-2", None, None, None, "UNIDENTIFIED", "UNIDENTIFIED", "FALLBACK-UNIDENTIFIED", 0.0)]
    size = write_submission(tmp_path, iter(rows))
    text = gzip.decompress((tmp_path / "submission.csv.gz").read_bytes())
    assert size == len(text)
    assert text.decode().splitlines()[1:] == ["BT-1,ARI-1,12.34,,PARTIAL", "BT-1,ARC-2,5.00,,",
                                            "BT-2,,,UNIDENTIFIED,UNIDENTIFIED"]


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

from __future__ import annotations

import polars as pl

from closebooks.diff import classify, exception_matrix

GOLDEN = pl.DataFrame({
    "bank_txn_id": ["A", "A", "B", "C", "D", "E", "F"],
    "item_id": ["I1", "I2", "I3", "I4", None, "I6", "I7"],
    "amount_cents": [100, 200, 300, 400, None, 600, 700],
    "category": [None, None, None, None, "BANK_FEES", None, None],
    "exception": ["", "", "", "PARTIAL", "", "", ""],
    "segment": ["s1", "s1", "s2", "s2", "s3", "s4", "s5"],
})
SUBMITTED = pl.DataFrame({
    "bank_txn_id": ["A", "B", "C", "D", "E", "E", "F"],
    "item_id": ["I1", "I3", "I4", None, "I6", "I9", None],
    "amount_cents": [100, 310, 400, None, 600, 50, None],
    "category": [None, None, None, "PAYROLL", None, None, "UNIDENTIFIED"],
    "exception": ["", "", "", "", "", "", "UNIDENTIFIED"],
    "rule": ["R", "R", "R", "CAT", "R", "R", "FALLBACK-UNIDENTIFIED"],
})


def test_each_wrong_line_gets_one_cause():
    causes = dict(zip(*classify(GOLDEN, SUBMITTED).select("bank_txn_id", "cause").get_columns(), strict=True))
    assert causes == {"A": "missing_item", "B": "wrong_amount", "C": "wrong_exception", "D": "wrong_category",
                      "E": "extra_item", "F": "not_matched"}


def test_line_within_tolerance_is_not_listed():
    golden = pl.DataFrame({"bank_txn_id": ["A"], "item_id": ["I"], "amount_cents": [100000], "category": [None],
                           "exception": [""], "segment": ["s"]}, schema_overrides={"category": pl.String})
    sub = pl.DataFrame({"bank_txn_id": ["A"], "item_id": ["I"], "amount_cents": [100400], "category": [None],
                        "exception": [""], "rule": ["R"]}, schema_overrides={"category": pl.String})
    assert classify(golden, sub).height == 0


def test_matrix_counts_false_positive_and_negative_and_points_lost():
    table = exception_matrix(GOLDEN, SUBMITTED)
    partial = table.filter(pl.col("exception") == "PARTIAL").row(0, named=True)
    assert (partial["golden"], partial["tp"], partial["fn"], partial["fp"]) == (1, 0, 1, 0)
    # A single class present in the golden carries the whole 20 of the macro-F1.
    assert partial["points_lost"] == 20.0

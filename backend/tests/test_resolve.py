from __future__ import annotations

from closebooks.categories import fallback
from closebooks.policy import decide
from closebooks.state import OpenBalances


def txn(amount_cents: int, **kw):
    return {"bank_txn_id": "BT-1", "amount_cents": amount_cents, "currency": "EUR", "bank": "X", "bank_code": "",
            "bank_subcode": "", "text": "", **kw}


def test_receipt_without_evidence_is_unidentified_never_a_guess():
    out = fallback(txn(12697))
    assert (out.category, out.exception, out.rule) == ("UNIDENTIFIED", "UNIDENTIFIED", "FALLBACK-UNIDENTIFIED")


def test_debit_without_evidence_gets_a_category_and_no_exception():
    out = fallback(txn(-1500))
    assert out.category == "BANK_FEES"
    assert out.exception == ""
    assert out.rule == "FALLBACK-CATEGORY"


def test_balance_decreases_on_payment_and_reopens_on_return():
    b = OpenBalances({"ARI-1": 1000})
    b.apply("ARI-1", 400, "", "BT-1", "2025-01-01")
    assert b.open("ARI-1") == 600
    b.apply("ARI-1", 600, "", "BT-2", "2025-01-02")
    assert b.open("ARI-1") == 0
    b.apply("ARI-1", 1000, "RETURNED", "BT-3", "2025-01-03")
    assert b.open("ARI-1") == 1000
    assert [h["bankTxnId"] for h in b.history("ARI-1")] == ["BT-1", "BT-2", "BT-3"]


def test_duplicate_payment_does_not_move_the_balance():
    b = OpenBalances({"ARI-1": 0})
    b.apply("ARI-1", 1000, "DUPLICATE_PAYMENT", "BT-1", "2025-01-01")
    assert b.open("ARI-1") == 0


def test_default_amount_is_the_open_balance_and_stated_cash_wins():
    assert decide(open_cents=1000, applied_cents=None) == (1000, "")
    assert decide(open_cents=1000, applied_cents=400) == (400, "")

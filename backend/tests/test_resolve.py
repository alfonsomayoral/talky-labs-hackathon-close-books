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


def line(open_cents, applied=None, *, item="API-1", item_currency="EUR", txn_currency="EUR", returned=False):
    return decide(item_id=item, item_currency=item_currency, txn_currency=txn_currency, open_cents=open_cents,
                  applied_cents=applied, returned=returned)


def test_payment_of_the_open_balance_clears_with_no_exception():
    assert line(1000) == (1000, "")
    assert line(1000, 1000) == (1000, "")


def test_payment_of_less_than_the_balance_is_partial_for_what_was_applied():
    assert line(1000, 400) == (400, "PARTIAL")


def test_invoice_paid_from_an_account_in_another_currency_is_fx_at_full_amount():
    assert line(1000, 1000, item_currency="USD", txn_currency="EUR") == (1000, "FX_DIFFERENCE")


def test_partial_keeps_its_code_and_credit_note_stays_empty_in_a_foreign_currency_line():
    assert line(1000, 400, item_currency="USD") == (400, "PARTIAL")
    assert line(1000, 1000, item="APC-1", item_currency="USD") == (1000, "")


def test_paying_an_item_already_settled_is_a_duplicate_of_what_was_paid_again():
    assert line(0, 1000) == (1000, "DUPLICATE_PAYMENT")


def test_returned_operation_reopens_the_amount_of_the_original_allocation():
    assert line(0, 1000, returned=True) == (1000, "RETURNED")

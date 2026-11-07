"""A later line that pays what an earlier deduction left open. Invented cases, none from the golden."""
from __future__ import annotations

from test_party_amount import item
from test_split_invoice import phase_of, receipt

from closebooks import rules
from closebooks.model import Proposal
from closebooks.resolve import resolve

NUMBER = "FV24-0326004"
INVOICE = "ARI-1"
TOTAL, DEDUCTED = 100000, 4067


def invoice(**extra):
    return item(INVOICE, "C1", NUMBER, TOTAL, **extra)


def line(cents=DEDUCTED, numbers=(NUMBER,), txn_id="BT-2", date="2024-06-20", **extra):
    return {**receipt(txn_id, cents, numbers, date), **extra}


def advice(reason="PRICE DIFF", deducted=DEDUCTED):
    """As ADVICE-* proposes the line of an advice with a deduction."""
    return {"BT-1": Proposal(rule="ADVICE-CSV", lines=[(INVOICE, TOTAL - deducted)],
                             deductions={INVOICE: (-deducted, reason)})}


def walk(items, txns, proposals):
    phase = phase_of(items, [line(TOTAL - DEDUCTED, (), "BT-1", "2024-06-01"), *txns])
    rows, _ = resolve(phase, proposals, rules.stateful(phase, proposals))
    return {(r.bank_txn_id, r.item_id): r for r in rows}


def test_it_pays_exactly_what_the_deduction_left_and_settles_that_invoice_without_exception():
    # An older invoice of the same amount: by amount alone the line would go there.
    older = item("ARI-0", "C1", "FV24-0100001", DEDUCTED, issued="2023-01-01")
    row = walk([older, invoice()], [line()], advice())["BT-2", INVOICE]
    assert (row.amount_cents, row.exception, row.rule) == (DEDUCTED, None, "REF-SETTLEMENT")


def test_its_evidence_is_the_line_that_deducted():
    row = walk([invoice()], [line()], advice())["BT-2", INVOICE]
    assert {"kind": "bankLine", "ref": "BT-1"} in row.sources


def test_in_another_currency_it_compares_the_amount_in_the_invoice_currency():
    txns = [line(cents=3500, currency="EUR", orig_cents=DEDUCTED, orig_currency="USD")]
    row = walk([invoice(currency="USD")], txns, advice())["BT-2", INVOICE]
    assert (row.amount_cents, row.exception, row.rule) == (DEDUCTED, "FX_DIFFERENCE", "REF-SETTLEMENT")


def test_a_cash_other_than_the_balance_is_not_this_rule():
    rows = walk([invoice()], [line(cents=DEDUCTED - 1)], advice())
    assert rows["BT-2", INVOICE].rule != "REF-SETTLEMENT"


def test_a_balance_left_without_a_stated_reason_is_not_a_dispute():
    rows = walk([invoice()], [line()], advice(reason=None))
    assert rows["BT-1", INVOICE].exception == "PARTIAL"
    assert rows["BT-2", INVOICE].rule != "REF-SETTLEMENT"


def test_an_invoice_without_history_is_not_this_rule():
    rows = walk([invoice()], [line()], {})
    assert rows.get(("BT-2", INVOICE)) is None or rows["BT-2", INVOICE].rule != "REF-SETTLEMENT"


def test_two_invoices_cited_say_nothing_about_which_one_it_settles():
    other = item("ARI-2", "C1", "FV24-0326005", 50000)
    rows = walk([invoice(), other], [line(numbers=(NUMBER, "FV24-0326005"))], advice())
    assert all(r.rule != "REF-SETTLEMENT" for key, r in rows.items() if key[0] == "BT-2")


def test_the_same_number_in_another_entity_is_not_cited():
    rows = walk([invoice()], [line(entity="E2")], advice())
    assert all(r.rule != "REF-SETTLEMENT" for key, r in rows.items() if key[0] == "BT-2")

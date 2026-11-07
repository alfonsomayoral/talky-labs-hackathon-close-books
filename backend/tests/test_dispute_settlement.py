"""A later line that pays what an earlier deduction left open. Invented cases, none from the golden."""
from __future__ import annotations

from test_party_amount import item
from test_split_invoice import phase_of, receipt

from closebooks import rules
from closebooks.model import Proposal
from closebooks.resolve import resolve
from closebooks.rules import dispute_settlement

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


# --- the two marks: the earlier line may have gone unseen, and the balance says nothing ---------------------------


def marked(cents=DEDUCTED, text=f"TRANSFERENCIAS PISCINAS ALAMEDA | REGULARIZACION {NUMBER}", **extra):
    return line(cents, (), text=text, **extra)


def proposed(items, txns):
    return dispute_settlement.propose(phase_of(items, txns))


def walk_marked(items, txns):
    phase = phase_of(items, txns)
    proposals = dispute_settlement.propose(phase)
    rows, balances = resolve(phase, proposals, rules.stateful(phase, proposals))
    return [(r.bank_txn_id, r.item_id, r.amount_cents, r.exception) for r in rows], balances


def test_a_mark_pays_less_than_our_balance_because_we_missed_the_earlier_line_and_has_no_exception():
    rows, balances = walk_marked([invoice()], [marked()])
    assert rows == [("BT-2", INVOICE, DEDUCTED, None)]
    assert balances.open(INVOICE) == TOTAL - DEDUCTED


def test_a_mark_pays_more_than_our_balance_and_the_amount_is_still_what_it_paid():
    rows, _ = walk_marked([invoice(open_cents=100)], [marked()])
    assert rows == [("BT-2", INVOICE, DEDUCTED, None)]


def test_the_english_mark_counts_with_the_number_in_the_remittance_field():
    txns = [marked(text="ACH CREDIT PISCINAS", remittance_info=f"SETTLEMENT {NUMBER}")]
    found = proposed([invoice()], txns)
    assert found["BT-2"].rule == "REF-SETTLEMENT-MARK"
    assert found["BT-2"].lines == [(INVOICE, DEDUCTED)]


def test_a_mark_in_another_currency_applies_the_amount_in_the_invoice_currency_with_fx_difference():
    rows, _ = walk_marked([invoice(currency="USD")], [marked(orig_cents=5000, orig_currency="USD")])
    assert rows == [("BT-2", INVOICE, 5000, "FX_DIFFERENCE")]


def test_a_mark_in_another_currency_without_the_amount_in_the_invoice_currency_claims_nothing():
    assert proposed([invoice(currency="USD")], [marked()]) == {}


def test_a_mark_with_two_invoices_cited_says_nothing_about_which_one_it_settles():
    other = item("ARI-2", "C1", "FV24-0326005", 50000)
    assert proposed([invoice(), other], [marked(text=f"SETTLEMENT {NUMBER} FV24-0326005")]) == {}


def test_any_other_wording_falls_back_to_what_the_other_rules_do():
    assert proposed([invoice()], [marked(text=f"RESTANTE {NUMBER}")]) == {}


def test_a_card_settlement_says_the_mark_and_cites_no_invoice():
    assert proposed([invoice()], [marked(text="CARD SETTLEMENT MID 328698493 2025-12-29")]) == {}


def test_a_debit_settles_nothing_of_ours():
    assert proposed([invoice()], [marked(cents=-DEDUCTED)]) == {}


def test_the_earlier_payment_can_still_take_the_invoice_the_mark_cites():
    paid = {**receipt("BT-1", TOTAL, (), "2024-06-01"), "text": "TRANSFERENCIA PISCINAS ALAMEDA"}
    rows, _ = walk_marked([invoice()], [paid, marked()])
    assert rows == [("BT-1", INVOICE, TOTAL, None), ("BT-2", INVOICE, DEDUCTED, None)]

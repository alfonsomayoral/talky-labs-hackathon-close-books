"""A receipt still unidentified after every rule, from one known customer: its oldest due invoices that fit the cash."""
from __future__ import annotations

from types import SimpleNamespace

import polars as pl
from test_late_party_amount import fallback, line
from test_party_amount import item, masters
from test_split_invoice import CUSTOMERS

from closebooks.model import Row
from closebooks.rules import party_guess
from closebooks.rules.party_amount import PartyAmount
from closebooks.state import OpenBalances

NAMED = "COBRO PISCINAS ALAMEDA"  # names C1 only
BOTH = "COBRO PISCINAS ALAMEDA RIEGOS VALLEJO"  # names C1 and C2


def invoice(item_id, cents, due, party="C1", issued="2024-01-01"):
    return {**item(item_id, party, f"FA{item_id}", cents, issued=issued), "due_date": due}


def run(items, txns, before=()):
    table = pl.DataFrame(items, schema_overrides={"customer_po": pl.String})
    frame = pl.DataFrame(txns, schema_overrides={
        k: pl.String for k in ("orig_currency", "remittance_info", "ref1", "ref2", "end_to_end_id",
                               "counterparty_account", "counterparty_name")} | {"orig_cents": pl.Int64,
                                                                                "amount_eur_cents": pl.Int64})
    phase = SimpleNamespace(items=table, masters=masters(CUSTOMERS), start="2021-01-01", txns=frame)
    engine = PartyAmount(phase, reserved={})
    balances = OpenBalances(dict(zip(table["item_id"], table["open_cents"], strict=True)))
    seen = {r.bank_txn_id for r in before}
    rows = [*before, *(fallback(t["bank_txn_id"]) for t in txns if t["bank_txn_id"] not in seen)]
    party_guess.apply(phase, rows, balances, engine)
    return rows, balances


def guessed(rows, txn_id="BT-1"):
    return [(r.item_id, r.amount_cents) for r in rows if r.bank_txn_id == txn_id]


def test_one_known_customer_gets_its_oldest_due_invoices_that_fit_the_cash():
    items = [invoice("ARI-3", 30000, "2024-04-01"), invoice("ARI-1", 10000, "2024-02-01"),
             invoice("ARI-2", 20000, "2024-03-01")]
    rows, balances = run(items, [line(cents=35000, text=NAMED)])
    assert guessed(rows) == [("ARI-1", 10000), ("ARI-2", 20000)]
    assert {(r.rule, r.exception, r.category, r.party_id) for r in rows} == {("PARTY-GUESS", None, None, "C1")}
    assert (balances.open("ARI-1"), balances.open("ARI-2"), balances.open("ARI-3")) == (0, 0, 30000)


def test_at_most_three_invoices():
    items = [invoice(f"ARI-{n}", 1000, f"2024-0{n}-01") for n in range(1, 7)]
    rows, _ = run(items, [line(cents=6000, text=NAMED)])
    assert guessed(rows) == [("ARI-1", 1000), ("ARI-2", 1000), ("ARI-3", 1000)]


def test_two_possible_customers_stay_unidentified():
    items = [invoice("ARI-1", 10000, "2024-02-01"), invoice("ARI-2", 10000, "2024-02-01", party="C2")]
    rows, _ = run(items, [line(cents=10000, text=BOTH)])
    assert [(r.item_id, r.exception, r.rule) for r in rows] == [(None, "UNIDENTIFIED", "FALLBACK-UNIDENTIFIED")]


def test_no_named_customer_stays_unidentified():
    rows, _ = run([invoice("ARI-1", 10000, "2024-02-01")], [line(cents=10000, text="TRANSFERENCIA RECIBIDA")])
    assert [r.rule for r in rows] == ["FALLBACK-UNIDENTIFIED"]


def test_cash_below_the_oldest_invoice_stays_unidentified():
    items = [invoice("ARI-1", 50000, "2024-02-01"), invoice("ARI-2", 1000, "2024-03-01")]
    rows, _ = run(items, [line(cents=20000, text=NAMED)])
    assert [r.rule for r in rows] == ["FALLBACK-UNIDENTIFIED"]


def test_an_invoice_already_due_and_left_open_by_an_earlier_receipt_of_the_customer_is_skipped():
    # The customer paid on 2024-04-15 and left ARI-1, due in February, open: it is not what it pays now.
    items = [invoice("ARI-1", 10000, "2024-02-01"), invoice("ARI-2", 20000, "2024-05-01"),
             invoice("ARI-9", 5000, "2024-04-01")]
    earlier = line("BT-0", 5000, NAMED, date="2024-04-15")
    paid = Row("BT-0", "ARI-9", 5000, "EUR", None, None, "REF-EXACT", 1.0, "C1")
    rows, _ = run(items, [earlier, line(cents=20000, text=NAMED)], before=[paid])
    assert guessed(rows) == [("ARI-2", 20000)]


def test_a_later_receipt_does_not_take_what_an_earlier_guess_took():
    items = [invoice("ARI-1", 10000, "2024-02-01"), invoice("ARI-2", 10000, "2024-03-01")]
    rows, _ = run(items, [line("BT-2", 10000, NAMED, date="2024-06-02"), line("BT-1", 10000, NAMED)])
    assert (guessed(rows, "BT-1"), guessed(rows, "BT-2")) == ([("ARI-1", 10000)], [("ARI-2", 10000)])


def test_the_oldest_invoice_alone_with_an_excess_within_the_policy_limits_is_an_overpayment():
    items = [invoice("ARI-1", 100000, "2024-02-01"), invoice("ARI-2", 50000, "2024-03-01")]
    rows, balances = run(items, [line(cents=101000, text=NAMED)])
    assert [(r.item_id, r.amount_cents, r.exception) for r in rows] == [("ARI-1", 100000, "OVERPAYMENT")]
    assert (balances.open("ARI-1"), balances.open("ARI-2")) == (0, 50000)


def test_a_guess_whose_leftover_is_beyond_the_limits_has_no_exception():
    items = [invoice("ARI-1", 100000, "2024-02-01"), invoice("ARI-2", 50000, "2024-03-01")]
    rows, _ = run(items, [line(cents=130017, text=NAMED)])
    assert [(r.item_id, r.exception) for r in rows] == [("ARI-1", None)]


def test_the_only_invoice_the_cash_overpays_beats_an_older_one_it_would_merely_cover():
    """BT-2025-0160296: 577,00 paying 477,00 in full, with 148,69 older and still open."""
    items = [invoice("ARI-OLD", 14869, "2024-02-01"), invoice("ARI-PAID", 47700, "2024-03-01")]
    rows, balances = run(items, [line(cents=57700, text=NAMED)])
    assert [(r.item_id, r.amount_cents, r.exception) for r in rows] == [("ARI-PAID", 47700, "OVERPAYMENT")]
    assert (balances.open("ARI-OLD"), balances.open("ARI-PAID")) == (14869, 0)


def test_the_only_invoice_the_cash_overpays_is_taken_when_the_oldest_exceeds_the_cash():
    items = [invoice("ARI-OLD", 90000, "2024-02-01"), invoice("ARI-PAID", 47700, "2024-03-01")]
    rows, _ = run(items, [line(cents=57700, text=NAMED)])
    assert [(r.item_id, r.exception) for r in rows] == [("ARI-PAID", "OVERPAYMENT")]


def test_two_invoices_the_cash_could_overpay_tell_nothing_and_the_oldest_stays():
    items = [invoice("ARI-1", 10000, "2024-02-01"), invoice("ARI-2", 47700, "2024-03-01"),
             invoice("ARI-3", 52700, "2024-04-01")]
    rows, _ = run(items, [line(cents=57700, text=NAMED)])
    assert guessed(rows) == [("ARI-1", 10000), ("ARI-2", 47700)]


def test_oldest_invoices_summing_to_the_cash_are_not_replaced_by_an_overpayment():
    items = [invoice("ARI-1", 20000, "2024-02-01"), invoice("ARI-2", 37700, "2024-03-01"),
             invoice("ARI-3", 47700, "2024-04-01")]
    rows, _ = run(items, [line(cents=57700, text=NAMED)])
    assert guessed(rows) == [("ARI-1", 20000), ("ARI-2", 37700)]



def test_of_several_customers_named_the_owner_of_the_only_invoice_the_cash_overpays_is_the_payer():
    # BT-2025-0011894: 2,246.03 for 2,146.03 (+100), a cut name that several customers start with.
    items = [invoice("ARI-OTHER", 50000, "2024-11-01"), invoice("ARI-2024-6925362", 214603, "2024-12-30", party="C2")]
    rows, balances = run(items, [line(cents=224603, text=BOTH)])
    assert [(r.item_id, r.amount_cents, r.exception, r.party_id, r.rule) for r in rows] == [
        ("ARI-2024-6925362", 214603, "OVERPAYMENT", "C2", "PARTY-GUESS")]
    assert rows[0].confidence < 0.5 and "inferred" in rows[0].candidates[0]["why"]
    assert (balances.open("ARI-OTHER"), balances.open("ARI-2024-6925362")) == (50000, 0)


def test_two_customers_named_with_an_invoice_the_cash_overpays_stay_unidentified():
    items = [invoice("ARI-1", 214603, "2024-12-30"), invoice("ARI-2", 214603, "2024-12-30", party="C2")]
    rows, _ = run(items, [line(cents=224603, text=BOTH)])
    assert [r.rule for r in rows] == ["FALLBACK-UNIDENTIFIED"]


def test_of_several_customers_named_a_cash_that_overpays_nothing_stays_unidentified():
    items = [invoice("ARI-1", 100000, "2024-12-30"), invoice("ARI-2", 50000, "2024-12-30", party="C2")]
    rows, _ = run(items, [line(cents=130017, text=BOTH)])
    assert [r.rule for r in rows] == ["FALLBACK-UNIDENTIFIED"]

"""A receipt left in fallback, the payer named however the bank prints it, and the only invoice open for that cash."""
from __future__ import annotations

from types import SimpleNamespace

import polars as pl
from test_party_amount import item, masters
from test_split_invoice import CUSTOMERS, receipt

from closebooks.cases import build_cases
from closebooks.model import Row
from closebooks.rules import late_party_amount
from closebooks.rules.party_amount import PartyAmount
from closebooks.state import OpenBalances

FALLBACK = "FALLBACK-UNIDENTIFIED"
INVOICE = "ARI-1"
CUT = "COBRO PISCINAS ALAMED RECIBO"
OUTSIDER = "Recaudaciones Norte"  # names nobody: only the text can say who paid
HOMONYM = ("C3", "E1", "Piscinas Alameda S.L.", None, None, None, None, None)
ROBLEDO = ("C4", "E1", "Piscinas Robledo S.L.", None, None, None, None, None)
REVERSED = ("C5", "E1", "Alameda Piscinas S.L.", None, None, None, None, None)
LONGER = ("C6", "E1", "Alameda Piscinas Norte S.L.", None, None, None, None, None)
ONE_WORD = ("C7", "E1", "Vallejo S.L.", None, None, None, None, None)


def line(txn_id="BT-1", cents=50000, text=CUT, name=OUTSIDER, date="2024-06-01", currency="EUR", **extra):
    return {**receipt(txn_id, cents, (), date, name, currency), "text": text, **extra}


def fallback(txn_id="BT-1"):
    return Row(txn_id, None, None, None, "UNIDENTIFIED", "UNIDENTIFIED", FALLBACK, 0.0)


def invoice(item_id=INVOICE, party="C1", cents=50000, **kw):
    return item(item_id, party, f"FA{item_id[-2:]}", cents, **kw)


def run(items, txns, rows=None, paid=(), customers=CUSTOMERS, suppliers=()):
    table = pl.DataFrame(items, schema_overrides={"customer_po": pl.String})
    frame = pl.DataFrame(txns, schema_overrides={
        k: pl.String for k in ("orig_currency", "remittance_info", "ref1", "ref2", "end_to_end_id",
                               "counterparty_account", "counterparty_name")} | {"orig_cents": pl.Int64,
                                                                                "amount_eur_cents": pl.Int64})
    phase = SimpleNamespace(items=table, masters=masters(customers, suppliers), start="2021-01-01", txns=frame)
    engine = PartyAmount(phase, reserved={})
    balances = OpenBalances(dict(zip(table["item_id"], table["open_cents"], strict=True)))
    for payment in paid:
        balances.apply(*payment)
    rows = [fallback(t["bank_txn_id"]) for t in txns] if rows is None else rows
    late_party_amount.apply(phase, rows, balances, engine)
    return rows, balances, engine


def settled(items, txns, **kw):
    return [(r.item_id, r.party_id) for r in run(items, txns, **kw)[0]]


NOTHING = [(None, None)]


def test_a_cut_name_that_gives_one_customer_closes_its_only_invoice_with_that_balance():
    rows, balances, _ = run([invoice()], [line()])
    row = rows[0]
    assert (row.item_id, row.amount_cents, row.currency, row.exception, row.category, row.rule, row.party_id) == (
        INVOICE, 50000, "EUR", None, None, "PARTY-AMOUNT-LATE", "C1")
    assert balances.open(INVOICE) == 0
    assert [(h["bankTxnId"], h["exception"]) for h in balances.history(INVOICE)] == [("BT-1", "")]


def test_the_rest_of_an_invoice_is_its_balance_not_its_total():
    paid = [(INVOICE, 10000, "PARTIAL", "BT-9", "2024-05-01")]
    assert settled([invoice()], [line(cents=40000)], paid=paid) == [(INVOICE, "C1")]


def later_partial():
    return Row("BT-9", INVOICE, 10000, "EUR", None, "PARTIAL", "PARTY-FRACTION", 0.85, "C1")


def test_a_receipt_before_a_payment_left_partial_is_the_partial_and_the_later_one_closes():
    rows, balances, _ = run([invoice()], [line(cents=40000)], rows=[fallback(), later_partial()],
                            paid=[(INVOICE, 10000, "PARTIAL", "BT-9", "2024-07-01")])
    assert [(r.bank_txn_id, r.exception, r.rule) for r in rows] == [
        ("BT-1", "PARTIAL", "PARTY-AMOUNT-LATE"), ("BT-9", None, "PARTY-FRACTION")]
    assert [(h["bankTxnId"], h["exception"]) for h in balances.history(INVOICE)] == [("BT-1", "PARTIAL"), ("BT-9", "")]
    assert balances.open(INVOICE) == 0


def test_a_receipt_after_a_payment_left_partial_closes_the_invoice():
    rows, _, _ = run([invoice()], [line(cents=40000)], rows=[fallback(), later_partial()],
                     paid=[(INVOICE, 10000, "PARTIAL", "BT-9", "2024-05-01")])
    assert [(r.bank_txn_id, r.exception) for r in rows] == [("BT-1", None), ("BT-9", "PARTIAL")]


def test_a_receipt_before_a_payment_that_was_not_partial_settles_nothing():
    rows, _, _ = run([invoice()], [line(cents=40000)], rows=[fallback()],
                     paid=[(INVOICE, 10000, "SHORT_DISCOUNT", "BT-9", "2024-07-01")])
    assert rows[0].rule == FALLBACK


def test_a_later_payment_of_the_invoice_stays_last_in_its_history():
    paid = [(INVOICE, 10000, "PARTIAL", "BT-9", "2024-07-01")]
    _, balances, _ = run([invoice()], [line(cents=40000)], paid=paid)
    assert [h["bankTxnId"] for h in balances.history(INVOICE)] == ["BT-1", "BT-9"]


def test_the_words_of_the_name_in_another_order_give_the_customer():
    txn = line(text="COBRO PISCINAS REF ALAMEDA")
    assert settled([invoice(party="C5")], [txn], customers=(REVERSED,)) == [(INVOICE, "C5")]


def test_a_payer_named_whole_in_its_field_gives_the_customer():
    assert settled([invoice()], [line(text="TRANSFERENCIA", name="Piscinas Alameda S.L.")]) == [(INVOICE, "C1")]


def test_a_name_cut_across_two_fields_of_the_text_is_read_whole():
    almost = ("C8", "E1", "Piscinas Ala S.L.", None, None, None, None, None)
    txn = line(text="COBRO PISCINAS ALA | MEDA RECIBO")
    assert settled([invoice()], [txn], customers=(*CUSTOMERS, almost)) == [(INVOICE, "C1")]


def test_the_words_of_a_suppliers_name_are_not_a_customer():
    supplier = ("S1", "E1", "Alameda Piscinas S.L.", None)
    txn = line(text="COBRO PISCINAS REF ALAMEDA")
    assert settled([invoice(party="S1")], [txn], suppliers=(supplier,)) == NOTHING


def test_one_word_of_a_name_is_not_a_customer():
    assert settled([invoice(party="C7")], [line(text="COBRO DE VALLEJO")], customers=(ONE_WORD,)) == NOTHING


def test_of_the_names_whose_words_are_in_the_text_only_the_longest_counts():
    items = [invoice(party="C5")]
    txn = line(text="COBRO PISCINAS REF NORTE ALAMEDA")
    assert settled(items, [txn], customers=(REVERSED, LONGER)) == NOTHING


def test_of_the_names_that_start_alike_only_the_longest_counts():
    assert settled([invoice(party="C4")], [line()], customers=(*CUSTOMERS, ROBLEDO)) == NOTHING


def test_several_candidates_and_only_one_has_the_invoice():
    assert settled([invoice()], [line(name="Piscinas Alameda S.L.")], customers=(*CUSTOMERS, HOMONYM)) == [
        (INVOICE, "C1")]


def test_two_invoices_with_that_balance_of_one_customer_settle_nothing():
    assert settled([invoice(), invoice("ARI-2")], [line()]) == NOTHING


def test_two_invoices_with_that_balance_across_the_candidates_settle_nothing():
    items = [invoice(), invoice("ARI-2", party="C3")]
    assert settled(items, [line(name="Piscinas Alameda S.L.")], customers=(*CUSTOMERS, HOMONYM)) == NOTHING


def test_two_receipts_on_one_invoice_settle_nothing():
    txns = [line(), line("BT-2", date="2024-06-20")]
    assert settled([invoice()], txns) == [*NOTHING, *NOTHING]


def test_one_cent_off_the_balance_settles_nothing():
    assert settled([invoice()], [line(cents=50001)]) == NOTHING


def test_an_invoice_in_another_currency_settles_nothing():
    assert settled([invoice()], [line(currency="USD")]) == NOTHING


def test_a_foreign_instructed_amount_settles_nothing():
    txn = line(orig_cents=50000, orig_currency="USD")
    assert settled([invoice(currency="USD")], [txn]) == NOTHING


def test_an_invoice_issued_after_the_receipt_settles_nothing():
    assert settled([invoice(issued="2024-06-02")], [line()]) == NOTHING


def test_an_invoice_issued_on_the_date_of_the_receipt_counts():
    assert settled([invoice(issued="2024-06-01")], [line()]) == [(INVOICE, "C1")]


def test_a_credit_note_is_not_an_invoice():
    assert settled([invoice("ARC-1")], [line()]) == NOTHING


def test_with_no_payer_the_amount_alone_settles_nothing():
    assert settled([invoice()], [line(text="TRANSFERENCIA RECIBIDA")]) == NOTHING


def test_a_receipt_that_is_not_in_fallback_is_left_as_it_is():
    row = Row("BT-1", "ARI-9", 50000, "EUR", None, None, "PARTY-AMOUNT", 0.9, "C1")
    rows, _, _ = run([invoice()], [line()], rows=[row])
    assert rows == [row]


def test_it_stays_for_a_person_to_review_with_its_evidence_and_no_question():
    rows, _, engine = run([invoice()], [line(name="Piscinas Alameda S.L.")], customers=(*CUSTOMERS, HOMONYM))
    row = rows[0]
    assert row.confidence == 0.85
    assert row.sources == [{"kind": "customer", "ref": "C1"}]
    assert [(c["itemId"], c["amountCents"], c["currency"]) for c in row.candidates] == [(INVOICE, 50000, "EUR")]
    assert "C1" in row.candidates[0]["why"] and "C3" in row.candidates[0]["why"]
    txns = {"BT-1": {**line(name="Piscinas Alameda S.L."), "amount_eur_cents": 50000}}
    assert [(c["status"], c["rule"]) for c in build_cases(rows, txns, "2024-07-01")] == [
        ("needs_review", "PARTY-AMOUNT-LATE")]
    assert "BT-1" not in engine.abstentions


def test_what_the_engine_abstained_on_is_gone_once_settled(monkeypatch):
    real = PartyAmount.__init__

    def with_abstention(self, phase, reserved):
        real(self, phase, reserved)
        self.abstentions["BT-1"] = {"reason": "subsets", "options": []}

    monkeypatch.setattr(PartyAmount, "__init__", with_abstention)
    assert run([invoice()], [line()])[2].abstentions == {}

"""A customer already seen withholding pays a set net of a rate of POLICIES, found after the walk by date."""
from __future__ import annotations

from types import SimpleNamespace

import polars as pl
from test_party_amount import item, masters
from test_split_invoice import receipt

from closebooks.model import Row
from closebooks.rules import withheld_sets
from closebooks.rules.party_amount import PartyAmount
from closebooks.state import OpenBalances

CUSTOMER = (("C1", "E1", "Bien-Etre Gutierrez SARL", None, None, None, None, None),)
TEXT = "TRANSFER. EN DIV. | DAJBAHXX -BIEN-ETRE GUTIERREZ"
FALLBACK = Row("BT-1", None, None, None, "UNIDENTIFIED", "UNIDENTIFIED", "FALLBACK-UNIDENTIFIED", 0.0)
SEEN = Row("BT-0", "ARI-0", 100000, "EUR", None, "SHORT_WITHHOLDING", "PARTY-WITHHELD", 0.85, "C1")
PAID = {"ARI-1", "ARI-2", "ARI-3"}
CASH = 490555  # 0.90 x (1300.03 + 1058.98 + 3091.60)


def invoices():
    return [item("ARI-0", "C1", "FV0", 100000, open_cents=0), item("ARI-1", "C1", "FV1", 130003),
            item("ARI-2", "C1", "FV2", 105898), item("ARI-3", "C1", "FV3", 309160),
            item("ARI-5", "C1", "FV5", 412077), item("ARI-6", "C1", "FV6", 96341)]


def run(items=None, rows=None, cash=CASH, country="MA", text=TEXT, seen_cash=90000, seen_on="2024-05-01"):
    txn = {**receipt("BT-1", cash, (), "2024-06-01", CUSTOMER[0][2]), "text": text}
    witness = {**receipt("BT-0", seen_cash, (), seen_on, CUSTOMER[0][2]), "text": text}
    table = pl.DataFrame(items or invoices(), schema_overrides={"customer_po": pl.String,
                                                                "related_document": pl.String})
    frame = pl.DataFrame([witness, txn], schema_overrides={
        k: pl.String for k in ("orig_currency", "remittance_info", "ref1", "ref2", "end_to_end_id",
                               "counterparty_account", "counterparty_name")} | {"orig_cents": pl.Int64,
                                                                                "amount_eur_cents": pl.Int64})
    phase = SimpleNamespace(items=table, masters=masters(CUSTOMER), start="2021-01-01", txns=frame)
    engine = PartyAmount(phase, reserved={})
    engine.countries = {"C1": country}
    balances = OpenBalances(dict(zip(table["item_id"], table["open_cents"], strict=True)))
    rows = [SEEN, FALLBACK] if rows is None else rows
    for row in rows:
        if row.item_id and row.bank_txn_id == "BT-1":
            balances.apply(row.item_id, row.amount_cents, row.exception or "", "BT-1", "2024-06-01")
    withheld_sets.apply(phase, rows, balances, engine)
    return [r for r in rows if r.bank_txn_id == "BT-1"], balances


def test_the_only_set_net_of_a_rate_clears_in_full_with_the_exception():
    rows, balances = run()
    assert {r.item_id for r in rows} == PAID
    assert {r.exception for r in rows} == {"SHORT_WITHHOLDING"}
    assert {r.rule for r in rows} == {withheld_sets.RULE}
    assert sum(r.amount_cents for r in rows) == 130003 + 105898 + 309160
    assert balances.open("ARI-3") == 0 and balances.open("ARI-5") == 412077
    assert "SEEN_RATE" in rows[0].candidates[0]["why"] and "BT-0" in rows[0].candidates[0]["why"]
    assert {r.confidence for r in rows} == {0.85}  # below 0.9: the case goes to review


def test_a_customer_nobody_saw_withholding_stays_where_it_was():
    rows, _ = run(rows=[FALLBACK])
    assert [r.rule for r in rows] == ["FALLBACK-UNIDENTIFIED"]


def test_a_line_seen_only_later_is_no_witness():
    rows, _ = run(seen_on="2024-07-01")
    assert [r.rule for r in rows] == ["FALLBACK-UNIDENTIFIED"]


def test_a_witness_at_another_rate_is_not_the_same_signal():
    rows, _ = run(seen_cash=98500)  # 1.5 % of the witness; the only set of this cash is net of 10 %
    assert [r.rule for r in rows] == ["FALLBACK-UNIDENTIFIED"]


def test_an_exception_the_rate_does_not_explain_is_no_witness():
    rows, _ = run(seen_cash=70000)
    assert [r.rule for r in rows] == ["FALLBACK-UNIDENTIFIED"]


def test_a_customer_outside_the_countries_of_policies_stays_where_it_was():
    rows, _ = run(country="ES")
    assert [r.rule for r in rows] == ["FALLBACK-UNIDENTIFIED"]


def test_two_sets_that_explain_the_cash_abstain():
    twin = item("ARI-7", "C1", "FV7", 309160)
    rows, _ = run([*invoices(), twin])
    assert [r.rule for r in rows] == ["FALLBACK-UNIDENTIFIED"]


def test_a_citation_of_part_of_the_set_is_completed_and_its_balance_not_paid_twice():
    cited = Row("BT-1", "ARI-1", 130003, "EUR", None, None, "REF-TEXT", 0.9, "C1")
    rows, balances = run(rows=[SEEN, cited])
    assert {r.item_id for r in rows} == PAID
    assert {r.exception for r in rows} == {"SHORT_WITHHOLDING"}
    assert {r.rule for r in rows} == {withheld_sets.CITED_RULE}
    assert balances.open("ARI-1") == 0
    assert [(h["amountCents"], h["exception"]) for h in balances.history("ARI-1")] == [(130003, "SHORT_WITHHOLDING")]


def test_a_cited_row_that_is_not_part_of_any_such_set_stays():
    cited = Row("BT-1", "ARI-5", 412077, "EUR", None, None, "REF-TEXT", 0.9, "C1")
    rows, _ = run(rows=[SEEN, cited])
    assert [(r.item_id, r.rule) for r in rows] == [("ARI-5", "REF-TEXT")]

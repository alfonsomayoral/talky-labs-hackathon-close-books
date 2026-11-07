"""POLICIES §3: a customer of Mexico, Brazil or Morocco pays several invoices net of tax withheld at source.

Invented case copied from the official example ar_short_withholding: four invoices, 10 %, every one with the exception.
"""
from __future__ import annotations

from test_party_amount import engine, item, lines, txn

from closebooks.policy import Terms, allocate

CUSTOMER = (("C1", "E1", "Bien-Etre Gutierrez SARL", None, None, None, None, None),)
TEXT = "TRANSFER. EN DIV. | DAJBAHXX -BIEN-ETRE GUTIERREZ"
PAID = {"ARI-1", "ARI-2", "ARI-3", "ARI-4"}
CASH = 551079  # 0.90 x (1300.03 + 1058.98 + 3015.93 + 748.16)


def invoices():
    return [item("ARI-1", "C1", "FV25-050538", 130003), item("ARI-2", "C1", "FV25-050539", 105898),
            item("ARI-3", "C1", "FV25-050540", 301593), item("ARI-4", "C1", "FV25-050541", 74816),
            item("ARI-5", "C1", "FV25-050542", 412077), item("ARI-6", "C1", "FV25-050543", 96341)]


def withheld_engine(extra=(), country="MA"):
    rule, balances = engine([*invoices(), *extra], customers=CUSTOMER)
    rule.countries = {"C1": country}
    return rule, balances


def test_no_number_in_the_text_the_unique_set_net_of_the_rate_settles():
    rule, balances = withheld_engine()
    found = rule(txn(CASH, TEXT), balances)
    assert found.rule == "PARTY-WITHHELD"
    assert lines(found) == PAID


def test_the_four_invoices_of_the_official_example_are_cleared_whole_with_the_exception():
    totals = {"ARI-1": 130003, "ARI-2": 105898, "ARI-3": 301593, "ARI-4": 74816}
    items = [(i, t, Terms(None, None, "2024-01-01", t, "MA")) for i, t in totals.items()]
    assert allocate(CASH, items, "2024-06-01", False) == {i: (t, "SHORT_WITHHOLDING") for i, t in totals.items()}


def test_the_text_cites_part_of_the_list_and_the_rate_completes_it():
    rule, balances = withheld_engine()
    found = rule(txn(CASH, f"{TEXT} FACT FV25-050539"), balances)
    assert found.rule == "REF-WITHHELD"
    assert lines(found) == PAID


def test_a_cited_invoice_outside_every_set_net_of_the_rate_keeps_what_the_text_cites():
    rule, balances = withheld_engine()
    found = rule(txn(CASH, f"{TEXT} FACT FV25-050542"), balances)
    assert found.rule == "REF-TEXT"
    assert lines(found) == {"ARI-5"}


def test_the_cent_each_invoice_rounds_is_tolerated():
    rule, balances = withheld_engine()
    assert lines(rule(txn(CASH + 1, TEXT), balances)) == PAID


def test_a_customer_of_a_country_that_does_not_withhold_is_left_alone():
    rule, balances = withheld_engine(country="ES")
    assert rule(txn(CASH, TEXT), balances) is None


def test_an_invoice_whose_pdf_explains_its_own_shortfall_is_not_taxed():
    rule, balances = withheld_engine()
    rule.clauses = {"ARI-1": {"retention": {"pct": 10}}}
    assert rule(txn(CASH, TEXT), balances) is None


def test_an_open_credit_note_that_is_the_whole_difference_explains_the_cash_instead_of_the_tax():
    rule, balances = engine([item("ARI-1", "C1", "FV25-050538", 100000), item("ARI-2", "C1", "FV25-050539", 120000),
                             item("ARC-1", "C1", "ND25-000337", 22000)], customers=CUSTOMER)
    rule.countries = {"C1": "BR"}
    assert rule(txn(198000, TEXT), balances) is None


def test_two_sets_net_of_the_rate_are_no_evidence():
    rule, balances = withheld_engine([item("ARI-7", "C1", "FV25-050544", 130003)])
    assert rule(txn(CASH, TEXT), balances) is None

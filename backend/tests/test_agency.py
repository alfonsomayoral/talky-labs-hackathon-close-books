"""POLICIES §5.1: a collection agency pays for the customer. Cases made up after the official example of the segment."""
from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest
from test_party_amount import engine, item, lines, masters, txn

from closebooks.resolve import resolve

AGENCY = "RECOBROS AGORA S.L."
DEBTOR = (("C1", "E1", "Teresa Iglesias Gutierrez", None, None, None, None, None),)
CUT_NAME = "EXPTE 45553 TERESA IGLESIAS GUTI 10"


def resolved(rule, wire):
    book = masters(customers=DEBTOR)
    book["customers"] = book["customers"].with_columns(pl.lit("ES").alias("country"))
    book["payment_terms"] = pl.DataFrame(schema=dict.fromkeys(
        ["code", "early_payment_discount_pct", "discount_days"], pl.String))
    phase = SimpleNamespace(items=rule._known.with_columns(pl.lit(None, pl.String).alias("payment_terms")),
                            masters=book, txns=pl.DataFrame([dict(wire, bank="B", bank_code="", bank_subcode="",
                                                                amount_eur_cents=wire["amount_cents"])],
                                                           schema_overrides={"orig_cents": pl.Int64}))
    return resolve(phase, {}, rule)[0]


def test_agency_citing_a_tail_settles_that_invoice_with_its_own_rule_and_sources():
    rule, _ = engine([item("ARI-1", "C1", "FV21-0215074", 1198618), item("ARI-2", "C1", "FV21-0215075", 1198618)],
                     customers=DEBTOR)
    row = resolved(rule, txn(1198618, "VIR SEPA RECU", name=AGENCY, remit="EXPTE 45553 TERESA IGL FRA 0215074"))[0]
    assert (row.item_id, row.amount_cents, row.exception, row.rule) == ("ARI-1", 1198618, None, "REF-AGENCY")
    assert {"kind": "customer", "ref": "C1"} in row.sources and {"kind": "bankLine", "ref": "BT-1"} in row.sources


@pytest.mark.parametrize("field", ["ref1", "ref2", "end_to_end_id"])
def test_the_tail_may_come_in_any_reference_of_the_line(field):
    rule, balances = engine([item("ARI-1", "C1", "FV21-0215074", 1198618)], customers=DEBTOR)
    assert lines(rule({**txn(1198618, "VIR SEPA RECU", name=AGENCY), field: "0215074"}, balances)) == {"ARI-1"}


def test_agency_naming_a_cut_debtor_settles_its_only_open_invoice_of_that_amount():
    rule, _ = engine([item("ARI-1", "C1", "FA220100793", 1198618), item("ARI-2", "C1", "FA220100644", 1109832)],
                     customers=DEBTOR)
    row = resolved(rule, txn(1198618, "VIR SEPA RECU", name=AGENCY, remit=CUT_NAME))[0]
    assert (row.item_id, row.amount_cents, row.exception, row.rule) == ("ARI-1", 1198618, None, "PARTY-AGENCY")
    assert {"kind": "customer", "ref": "C1"} in row.sources


def test_named_debtor_with_two_open_invoices_of_the_amount_stays_unmatched():
    rule, balances = engine([item("ARI-1", "C1", "FA220100793", 1198618), item("ARI-2", "C1", "FA220100794", 1198618)],
                            customers=DEBTOR)
    assert rule(txn(1198618, "VIR SEPA RECU", name=AGENCY, remit=CUT_NAME), balances) is None


def test_a_tail_shared_by_two_open_invoices_of_the_amount_stays_unmatched():
    invoices = [item("ARI-1", "C1", "FV21-0215074", 1198618), item("ARI-2", "C2", "FV22-0215074", 1198618)]
    rule, balances = engine(invoices, customers=DEBTOR)
    assert rule(txn(1198618, "VIR SEPA RECU", name=AGENCY, remit="EXPTE 0215074"), balances) is None


def test_a_tail_of_another_entitys_invoice_stays_unmatched():
    rule, balances = engine([item("ARI-1", "C1", "FV21-0215074", 1198618, entity="E2")], customers=DEBTOR)
    assert rule(txn(1198618, "VIR SEPA RECU", name=AGENCY, remit="EXPTE 0215074"), balances) is None


def test_a_tail_or_a_name_with_another_amount_stays_unmatched():
    rule, balances = engine([item("ARI-1", "C1", "FV21-0215074", 1198619)], customers=DEBTOR)
    assert rule(txn(1198618, "VIR SEPA RECU", name=AGENCY, remit=f"{CUT_NAME} FRA 0215074"), balances) is None


def test_a_tail_of_four_digits_is_not_enough():
    rule, balances = engine([item("ARI-1", "C1", "FV21-0215074", 1198618)], customers=DEBTOR)
    assert rule(txn(1198618, "VIR SEPA RECU", name=AGENCY, remit="EXPTE 5074"), balances) is None


def test_an_invoice_a_file_reserves_is_not_the_agencys():
    rule, balances = engine([item("ARI-1", "C1", "FV21-0215074", 1198618)], customers=DEBTOR)
    rule.reserved = {"ARI-1": {"BT-9"}}
    assert rule(txn(1198618, "VIR SEPA RECU", name=AGENCY, remit=f"{CUT_NAME} FRA 0215074"), balances) is None


def test_a_credit_note_of_the_amount_is_not_what_an_agency_pays():
    rule, balances = engine([item("ARC-1", "C1", "AV22-0100025", 1198618)], customers=DEBTOR)
    assert rule(txn(1198618, "VIR SEPA RECU", name=AGENCY, remit=CUT_NAME), balances) is None


def test_a_payer_the_masters_know_is_not_an_agency():
    customers = (*DEBTOR, ("C2", "E1", "Riegos del Sur S.L.", None, None, None, None, None))
    rule, balances = engine([item("ARI-1", "C1", "FV21-0215074", 1198618)], customers=customers)
    assert rule(txn(1198618, "VIR SEPA RECU", name="Riegos del Sur S.L.", remit="FRA 0215074"), balances) is None


def test_a_lookalike_with_the_amount_but_no_name_nor_tail_is_unidentified():
    rule, _ = engine([item("ARI-1", "C1", "FV21-0215074", 1198618)], customers=DEBTOR)
    row = resolved(rule, txn(1198618, "VIR SEPA RECU", name=AGENCY, remit="EXPTE 45553 PEDRO RUIZ MARTIN 10"))[0]
    assert (row.item_id, row.category, row.exception) == (None, "UNIDENTIFIED", "UNIDENTIFIED")
    assert row.rule.startswith("FALLBACK-")


def test_the_official_example_in_mt940_already_comes_through_the_party_of_the_text():
    rule, balances = engine([item("ARI-1", "C1", "FA220100793", 1198618), item("ARI-2", "C1", "FA220100644", 1109832)],
                            customers=DEBTOR)
    wire = txn(1198618, "VIR SEPA RECU /DE RECOBROS ÁGORA, S.L. /MOTIF EXPTE 45553 TERESA IGLESIAS GUTI 10 /REF")
    found = rule(wire, balances)
    assert (found.rule, lines(found)) == ("PARTY-AMOUNT", {"ARI-1"})

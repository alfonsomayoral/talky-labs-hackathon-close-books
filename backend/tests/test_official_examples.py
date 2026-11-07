"""What the official examples page declares and the engine missed: invented names and amounts, the text forms of the
examples and of the bank files. Each one walks the line through the rules and resolve."""
from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest
from test_party_amount import item, masters, txn

from closebooks.documents.pdfs import clauses_from_text
from closebooks.resolve import resolve
from closebooks.rules.party_amount import PartyAmount


def customer(name, party="C1"):
    return (party, "E1", name, None, None, None, None, None)


def book(customers, country):
    out = masters(customers=customers)
    out["customers"] = out["customers"].with_columns(pl.lit(country).alias("country"))
    out["payment_terms"] = pl.DataFrame(schema=dict.fromkeys(
        ["code", "early_payment_discount_pct", "discount_days"], pl.String))
    return out


def walked(items, line, customers, *, country="ES", pdfs=None):
    """The rows of one bank line: (item, amount in cents, exception)."""
    table = pl.DataFrame(items, schema_overrides={"customer_po": pl.String}).with_columns(
        pl.lit(None, pl.String).alias("payment_terms"))
    bank = dict(line, bank="B", bank_code="", bank_subcode="", amount_eur_cents=line["amount_cents"])
    frame = pl.DataFrame([bank], schema_overrides={k: pl.String for k in (
        "ref1", "ref2", "end_to_end_id", "remittance_info", "counterparty_name", "counterparty_account",
        "orig_currency")} | {"orig_cents": pl.Int64})
    phase = SimpleNamespace(items=table, masters=book(customers, country), txns=frame, start="2021-01-01")
    rule = PartyAmount(phase, reserved={})
    rule.clauses = {i: {c.kind: c.value for c in clauses_from_text(text)} for i, text in (pdfs or {}).items()}
    rule.reindex()
    rows, _ = resolve(phase, {}, rule)
    return [(r.item_id, r.amount_cents, r.exception) for r in rows]


ROBLEDO = (customer("Robledo Piscinas S.L."),)
RETENTION_LINE = "TRANSF. A SU FAVOR | 51223344-ROBLEDO PISCINAS S.L. | PEDIDO PISCINA"
UNIDENTIFIED = [(None, None, "UNIDENTIFIED")]


def retention_pdf(pct, retained, payable):
    return (f"Retención en garantía del {pct} % ({retained} EUR), liberable a la recepción definitiva (19/11/2025). "
            f"Importe a pagar al vencimiento: {payable} EUR.")


def retention_rows(total, pdf, cash, *, line=RETENTION_LINE, name=None, country="ES"):
    return walked([item("ARI-1", "C1", "FV24-0400001", total)], txn(cash, line, name=name), ROBLEDO, country=country,
                  pdfs={"ARI-1": pdf})


@pytest.mark.parametrize(
    ("total", "pdf", "cash"),
    [(3056128, retention_pdf("10", "3.056,12", "27.505,16"), 2750515),
     (100012, retention_pdf("5", "50,00", "950,12"), 95011),
     (100010, retention_pdf("5", "50,00", "950,10"), 95009),
     (100007, retention_pdf("5", "50,00", "950,07"), 95007),
     (100000, retention_pdf("5", "50,00", "950,00"), 95000),
     (100010, retention_pdf("7,5", "75,00", "925,10"), 92509)],
    ids=["10pct_above_half", "5pct_above_half", "5pct_tie", "5pct_below_half", "5pct_whole", "7_5pct_decimal"])
def test_retention_is_partial_for_the_total_less_the_percentage_rounded_half_up(total, pdf, cash):
    assert retention_rows(total, pdf, cash) == [("ARI-1", cash, "PARTIAL")]


@pytest.mark.parametrize(
    ("total", "pdf", "cash"),
    [(100000, retention_pdf("5", "50,00", "950,00"), 94999),
     (100012, retention_pdf("5", "50,00", "950,12"), 95012),
     (100010, retention_pdf("5", "50,00", "950,10"), 95010),
     (100012, retention_pdf("5", "50,00", "950,12"), 5000)],
    ids=["5pct_a_cent_below", "5pct_the_printed_payable", "5pct_tie_the_printed_payable",
         "5pct_the_printed_retention"])
def test_a_cash_the_percentage_does_not_give_settles_nothing(total, pdf, cash):
    assert retention_rows(total, pdf, cash) == UNIDENTIFIED


def test_a_cent_off_a_retention_of_a_withholding_rate_settles_nothing():
    pdf = retention_pdf("10", "1.640,50", "14.764,50")
    assert retention_rows(1640500, pdf, 1476449) == UNIDENTIFIED


@pytest.mark.parametrize(("line", "name"), [("INGRESO EN CUENTA", None), ("TRANSFERENCIA", "Otra Sociedad S.A.")],
                         ids=["no_party", "unknown_party"])
def test_the_amount_of_the_percentage_without_the_party_settles_nothing(line, name):
    pdf = retention_pdf("5", "50,00", "950,12")
    assert retention_rows(100012, pdf, 95011, line=line, name=name) == UNIDENTIFIED

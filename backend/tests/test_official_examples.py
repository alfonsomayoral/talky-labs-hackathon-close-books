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


def test_the_release_of_a_retention_whose_first_payment_we_did_not_see_settles_with_no_exception():
    pdf = retention_pdf("5", "50,00", "950,12")
    assert retention_rows(100012, pdf, 5001) == [("ARI-1", 5001, None)]


@pytest.mark.parametrize("country", ["MX", "BR", "MA"])
def test_a_retention_of_a_withholding_rate_is_partial_where_that_tax_exists(country):
    """POLICIES §3: the first payment of an invoice with a guarantee retention is PARTIAL; SHORT_WITHHOLDING is the tax
    some customers withhold. §5.8: only the PDF says an invoice retains, so its clause wins over the country."""
    pdf = retention_pdf("10", "1.640,50", "14.764,50")
    assert retention_rows(1640500, pdf, 1476450, country=country) == [("ARI-1", 1476450, "PARTIAL")]


def test_an_advance_of_a_withholding_rate_is_partial_where_that_tax_exists():
    pdf = "A deducir anticipo recibido según proforma PF24-0100009 de 100,00 EUR. Importe neto a pagar 900,00 EUR."
    line = txn(90000, "TRANSFERENCIA DE ROBLEDO PISCINAS S.L. | FRA. FV24-0113001")
    rows = walked([item("ARI-1", "C1", "FV24-0113001", 100000)], line, ROBLEDO, country="MX", pdfs={"ARI-1": pdf})
    assert rows == [("ARI-1", 90000, "PARTIAL")]


ADVANCE_NET = "A deducir anticipo recibido según proforma PF24-0100009 de 100,05 EUR. Importe neto a pagar 900,07 EUR."
ROBLEDO_LINE = "TRANSFERENCIA DE ROBLEDO PISCINAS S.L."


def test_the_net_of_an_advance_is_the_printed_one_with_no_rounding_of_a_percentage():
    rows = walked([item("ARI-1", "C1", "FV24-0113001", 100012)], txn(90006, ROBLEDO_LINE), ROBLEDO,
                  pdfs={"ARI-1": ADVANCE_NET})
    assert rows == UNIDENTIFIED


@pytest.mark.parametrize(("total", "pdf", "cash"), [(100012, retention_pdf("5", "50,00", "950,12"), 95011),
                                                    (100012, ADVANCE_NET, 90007)], ids=["retention", "advance"])
def test_a_cash_equal_to_what_an_invoice_issued_later_expects_is_not_its_payment(total, pdf, cash):
    """That cash is the customer_advance the invoice will deduct (POLICIES §4), not a payment of the invoice."""
    invoice = item("ARI-1", "C1", "FV24-0113001", total, "2024-07-01")
    assert walked([invoice], txn(cash, ROBLEDO_LINE, date="2024-06-01"), ROBLEDO, pdfs={"ARI-1": pdf}) == UNIDENTIFIED


def test_a_withholding_with_no_clause_stays_a_withholding():
    line = txn(90000, "TRANSFERENCIA DE ROBLEDO PISCINAS S.L. | FRA. FV24-0113001")
    rows = walked([item("ARI-1", "C1", "FV24-0113001", 100000)], line, ROBLEDO, country="MX")
    assert rows == [("ARI-1", 100000, "SHORT_WITHHOLDING")]

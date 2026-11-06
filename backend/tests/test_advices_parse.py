from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from closebooks.documents.advices import AdviceError, normalize_number, parse_advice, parse_advices

FIXTURES = Path(__file__).parent / "fixtures" / "advices"


def lines(advice):
    return [(x.document, x.gross_cents, x.deduction_cents, x.reason, x.paid_cents) for x in advice.lines]


def test_csv_with_a_stated_reason_keeps_deduction_reason_and_customer_order():
    advice = parse_advice(FIXTURES / "dispute.csv")
    assert (advice.fmt, advice.payment_ref, advice.payment_date, advice.currency) == (
        "csv", "9926100255", "2024-10-02", "USD")
    assert advice.total_cents == 173875 and advice.closes
    line = advice.lines[0]
    assert (line.document, line.doc_date, line.gross_cents, line.deduction_cents, line.reason, line.paid_cents,
            line.po) == ("1102416261", "2024-08-27", 179252, -5377, "SHORT DELIVERY", 173875, "4534082206")


def test_csv_with_semicolons_reads_a_credit_note_as_a_negative_line():
    advice = parse_advice(FIXTURES / "credit_note_semicolon.csv")
    assert lines(advice) == [("FV24-0401885", 65891, 0, None, 65891), ("AB24-0400077", -32945, 0, None, -32945)]
    assert advice.total_cents == 32946 and advice.closes


def test_csv_discount_line_among_plain_ones():
    advice = parse_advice(FIXTURES / "discount.csv")
    assert advice.lines[0].reason == "DISCOUNT" and advice.lines[0].deduction_cents == -3172
    assert [x.deduction_cents for x in advice.lines[1:]] == [0, 0, 0, 0]
    assert advice.total_cents == 1171765 and advice.closes


def test_txt_us_layout_reads_gross_deduction_and_the_payment_date_in_month_first_order():
    advice = parse_advice(FIXTURES / "discount_us.txt", received=date(2023, 1, 13))
    assert (advice.fmt, advice.payment_ref, advice.currency, advice.total_cents) == ("txt", "2379002796", "EUR", 614302)
    # 01/10/2023 written month first: the closest reading to the e-mail date of 13 Jan.
    assert advice.payment_date == "2023-01-10"
    assert lines(advice) == [("FV23-0300567", 620507, -6205, "DISCOUNT", 614302)]
    assert advice.lines[0].doc_date == "2023-01-05" and advice.closes


def test_txt_spanish_layout_uses_decimal_comma_and_negative_credit_note():
    advice = parse_advice(FIXTURES / "credit_note_es.txt", received=date(2025, 5, 19))
    assert (advice.payment_ref, advice.total_cents, advice.currency, advice.payment_date) == (
        "250519869471", 66822, "EUR", "2025-05-19")
    assert lines(advice) == [("FV24-0106009", 95459, 0, None, 95459), ("AB25-0100001", -28637, 0, None, -28637)]
    assert advice.closes


def test_old_xlsx_has_no_currency_and_reads_the_total_row():
    advice = parse_advice(FIXTURES / "old.xlsx")
    assert (advice.fmt, advice.payer, advice.payment_ref, advice.currency, advice.total_cents) == (
        "xlsx", "AAP Pools Ltd.", "8010050601", None, 510763)
    assert lines(advice) == [("1102207296", 521187, -10424, "DISCOUNT", 510763)] and advice.closes


def test_new_xlsx_keeps_our_number_without_prefix_the_voucher_and_the_po():
    advice = parse_advice(FIXTURES / "new.xlsx")
    assert (advice.payment_ref, advice.total_cents, len(advice.lines)) == ("REM/2025/0787", 2880056, 17)
    first, credit = advice.lines[0], advice.lines[-1]
    assert (first.document, first.voucher, first.po, first.gross_cents, first.deduction_cents, first.paid_cents) == (
        "106593", "VCHR23209939", "4528986946", 40408, -404, 40004)
    assert (credit.document, credit.po, credit.paid_cents) == ("100198", None, -86255)
    assert first.reason is None and advice.closes


def test_pdf_table_reads_rows_with_and_without_deduction():
    advice = parse_advice(FIXTURES / "deduction.pdf")
    assert (advice.fmt, advice.payment_ref, advice.currency, advice.total_cents) == (
        "pdf", "PAY-2022-001234", "CAD", 415813)
    assert lines(advice) == [("1092117440", 318692, -15934, "PRICE DIFF", 302758),
                             ("1092117320", 222793, 0, None, 222793),
                             ("CM092200047", -109738, 0, None, -109738)]
    assert advice.lines[0].doc_date == "2021-12-24" and advice.closes


def test_pdf_in_spanish_uses_its_own_labels_and_decimal_comma():
    advice = parse_advice(FIXTURES / "deduction_es.pdf")
    assert (advice.payment_ref, advice.currency, advice.total_cents) == ("PAY-2024-001559", "EUR", 684770)
    assert lines(advice) == [("FV24-0320420", 249766, -74929, "COOP MKT", 174837),
                             ("FV24-0320007", 509933, 0, None, 509933)]
    assert advice.closes


def test_a_line_paid_below_its_gross_without_a_stated_deduction_still_closes_on_the_paid_amounts(tmp_path):
    # The customer silently took a discount: gross 2031.74, paid 1991.11, no deduction and no reason printed.
    path = tmp_path / "RA_x.csv"
    path.write_text("payment_ref,1,payment_date,2021-07-26,currency,AUD\n"
                    "document,doc_date,gross,discount_or_deduction,reason,paid,your_order\n"
                    "INV21-0104938,15/06/2021,2031.74,,,1991.11,\nTOTAL,,,,,1991.11,\n")
    advice = parse_advice(path)
    line = advice.lines[0]
    assert (line.gross_cents, line.deduction_cents, line.reason, line.paid_cents) == (203174, 0, None, 199111)
    assert advice.closes


def test_an_advice_whose_lines_do_not_add_up_to_the_total_is_kept_but_does_not_close(tmp_path):
    text = (FIXTURES / "credit_note_semicolon.csv").read_text().replace("329.46", "329.47")
    path = tmp_path / "RA_x.csv"
    path.write_text(text)
    advice = parse_advice(path)
    assert advice.total_cents == 32947 and not advice.closes


def test_unknown_layout_and_corrupt_files_are_recorded_and_skipped(tmp_path):
    unknown = tmp_path / "unknown.csv"
    unknown.write_text("factura;importe\nA;1\n")
    broken_xlsx = tmp_path / "broken.xlsx"
    broken_xlsx.write_bytes(b"not a zip")
    broken_pdf = tmp_path / "broken.pdf"
    broken_pdf.write_bytes(b"%PDF-1.4 truncated")
    with pytest.raises(AdviceError):
        parse_advice(unknown)
    batch = parse_advices([(unknown, "a/unknown.csv"), (broken_xlsx, "a/broken.xlsx"), (broken_pdf, "a/broken.pdf"),
                           (FIXTURES / "old.xlsx", "a/old.xlsx")], workers=1)
    assert [a.path for a in batch.advices] == ["a/old.xlsx"]
    assert sorted(path for path, _ in batch.failures) == ["a/broken.pdf", "a/broken.xlsx", "a/unknown.csv"]


@pytest.mark.parametrize(("raw", "norm"), [
    ("FV24-0100298", "FV240100298"), ("fv24 0100298", "FV240100298"), ("0000312113", "312113"), ("312113", "312113"),
])
def test_normalize_number_drops_separators_case_and_leading_zeros_of_pure_numbers(raw, norm):
    assert normalize_number(raw) == norm


def test_facts_frame_has_one_row_per_line_with_the_contract_columns():
    from closebooks.documents.advices import AdviceBatch, documents_frame, residue
    from closebooks.output import DOCUMENT_SCHEMA

    advice = parse_advice(FIXTURES / "new.xlsx", rel="remittance_advices/CH01/new.xlsx")
    advice.entity, advice.received_date = "CH01", "2025-10-21"
    batch = AdviceBatch([advice], [("remittance_advices/CH01/bad.pdf", "no remittance table")])
    frame = documents_frame(batch)
    assert dict(frame.schema) == DOCUMENT_SCHEMA and frame.height == 17
    row = frame.row(0, named=True)
    assert (row["docPath"], row["docKind"], row["entity"], row["paymentRef"], row["paymentTotalCents"], row["lineNo"],
            row["documentNumber"], row["documentNumberNorm"], row["deductionCents"], row["voucher"], row["method"]) == (
        "remittance_advices/CH01/new.xlsx", "remittanceAdvice", "CH01", "REM/2025/0787", 2880056, 1, "106593", "106593",
        -404, "VCHR23209939", "parser")
    assert residue(batch) == {"xlsx": {"read": 1, "closed": 1, "failed": 0},
                              "pdf": {"read": 0, "closed": 0, "failed": 1}}

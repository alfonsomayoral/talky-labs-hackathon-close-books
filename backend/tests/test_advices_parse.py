from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from closebooks.documents.advices import AdviceError, normalize_number, parse_advice, parse_advices, read_cells

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


# Lines of the holdout's advices under headers nobody has seen: the numbers carry the year of their date.
HEADERS = "Beleg-Nr;Fecha doc;Importe bruto;Abzug;Motivo abzug;Liquidado;Pedido cliente"
BODY = """FV24-0305899;12/03/2024;11006.11;;;11006.11;4576522204
FV24-0311335;06/05/2024;1830.85;-54.93;SHORT DELIVERY;1775.92;4573673371
1102416261;25/06/2024;1447.39;;;1447.39;
TOTAL;;;;;14229.42;
"""


def invented(tmp_path, headers=HEADERS, body=BODY):
    path = tmp_path / "advice.csv"
    path.write_text(f"payment_ref;PAY-2024-002248;payment_date;2024-12-31;currency;EUR\n{headers}\n{body}")
    return path


def test_a_csv_with_invented_headers_is_read_by_what_its_columns_hold(tmp_path):
    advice = parse_advice(invented(tmp_path))
    assert advice.closes
    assert lines(advice) == [("FV24-0305899", 1100611, 0, None, 1100611),
                             ("FV24-0311335", 183085, -5493, "SHORT DELIVERY", 177592),
                             ("1102416261", 144739, 0, None, 144739)]
    assert advice.lines[0].doc_date == "2024-03-12"
    assert advice.lines[0].po == "4576522204"


def test_two_columns_that_could_be_the_document_number_are_rejected(tmp_path):
    body = BODY.replace("FV24-0305899", "ABC-1").replace("FV24-0311335", "ABC-2").replace("1102416261", "ABC-3")
    body = body.replace("4576522204", "PO-1").replace("4573673371", "PO-2").replace("1447.39;\n", "1447.39;PO-3\n")
    with pytest.raises(AdviceError):
        parse_advice(invented(tmp_path, body=body))


def test_an_invented_layout_whose_amounts_do_not_add_up_to_the_total_is_rejected(tmp_path):
    with pytest.raises(AdviceError):
        parse_advice(invented(tmp_path, body=BODY.replace("14229.42", "99.99")))


def test_an_invented_layout_with_no_total_is_rejected(tmp_path):
    with pytest.raises(AdviceError):
        parse_advice(invented(tmp_path, body=BODY.replace("TOTAL;;;;;14229.42;\n", "")))


# Two e-mails and two PDFs nobody has seen. Nothing but the arithmetic of the advice says which column is which.
MAIL = """Subject: Payment advice 250102632763
From: pay@customer.example
Date: Thu, 02 Jan 2025 09:00:00 +0000

Buenos dias,
Les confirmamos la transferencia emitida con el siguiente detalle.
Total ordenado: AUD 1,869.61 (fecha valor 01/02/2025).
Relacion de documentos liquidados:
Fecha doc;Documento;Importe;Descuento;Motivo
16/12/24;INV24-0126826;560.44
03/12/24;INV24-0125773;1,309.17
Un saludo,
Backyard Pty Ltd
"""
SHORT_MAIL = MAIL.replace("Total ordenado: AUD 1,869.61", "Total ordenado: AUD 1,769.61").replace(
    "03/12/24;INV24-0125773;1,309.17", "03/12/24;INV24-0125773;1,309.17;-100.00;DAMAGED GOODS")


def test_an_email_in_another_order_is_read_by_what_its_cells_hold(tmp_path):
    path = tmp_path / "advice.txt"
    path.write_text(MAIL)
    advice = parse_advice(path)
    assert advice.closes and advice.payment_ref == "250102632763" and advice.currency == "AUD"
    assert lines(advice) == [("INV24-0126826", 56044, 0, None, 56044), ("INV24-0125773", 130917, 0, None, 130917)]
    assert advice.lines[0].doc_date == "2024-12-16"


def test_an_email_with_a_deduction_in_another_order_keeps_gross_deduction_reason_and_paid(tmp_path):
    path = tmp_path / "advice.txt"
    path.write_text(SHORT_MAIL)
    advice = parse_advice(path)
    assert lines(advice)[1] == ("INV24-0125773", 130917, -10000, "DAMAGED GOODS", 120917)


def test_an_email_with_one_amount_per_line_and_another_total_is_read_but_does_not_close(tmp_path):
    # A discount taken without saying it: the known layouts read these too, and the cash has to agree with the total.
    path = tmp_path / "advice.txt"
    path.write_text(MAIL.replace("1,869.61", "1,800.00"))
    advice = parse_advice(path)
    assert advice.total_cents == 180000 and not advice.closes


def test_several_amounts_per_line_that_add_up_to_no_printed_total_are_rejected(tmp_path):
    path = tmp_path / "advice.txt"
    path.write_text(SHORT_MAIL.replace("1,769.61", "9,999.99"))
    with pytest.raises(AdviceError):
        parse_advice(path)


def test_an_email_with_two_numbers_per_line_and_no_year_to_tell_them_apart_is_rejected(tmp_path):
    body = MAIL.replace("INV24-0126826;560.44", "ABC-1;XYZ-7;560.44").replace(
        "INV24-0125773;1,309.17", "ABC-2;XYZ-8;1,309.17")
    path = tmp_path / "advice.txt"
    path.write_text(body)
    with pytest.raises(AdviceError):
        parse_advice(path)


CELLS = """Notificacion de transferencia
Referencia de pago: REM/2025/1771
Fecha valor: 30/05/2025
Total: AUD 3,869.61
Factura
Fecha doc.
Liquidado
Importe doc.
Descuento
Motivo
INV25-0310764
30/04/2025
1,869.61
2,670.86
-801.25
DAMAGED GOODS
GS250100170
15/04/2025
-500.00
-500.00
INV25-0310999
02/05/2025
2,500.00
2,500.00
"""


def test_a_table_of_loose_cells_with_paid_before_gross_is_read_by_what_they_hold():
    advice = read_cells(CELLS.split("\n"), "pdf", "x.pdf", None)
    assert advice.closes and advice.payment_ref == "REM/2025/1771" and advice.currency == "AUD"
    assert lines(advice) == [("INV25-0310764", 267086, -80125, "DAMAGED GOODS", 186961),
                             ("GS250100170", -50000, 0, None, -50000), ("INV25-0310999", 250000, 0, None, 250000)]


def test_paid_before_gross_with_no_deduction_column_reads_the_shortfall(tmp_path):
    # RA_20250115: 2.485,23 of 2.535,95, unsaid; the bigger of the two amounts of a line is what the document was worth.
    cells = ["Total: AUD 7,776.29", "Fecha doc.", "03/01/2025", "INV25-0100504", "2,485.23", "2,535.95",
             "10/12/2024", "INV24-0126363", "5,291.06", "5,291.06", "Referencia 250110274015"]
    advice = read_cells(cells[:-1], "pdf", "x.pdf", None, ref="250110274015")
    assert lines(advice)[0] == ("INV25-0100504", 253595, -5072, None, 248523)


def test_a_total_in_the_foot_is_never_the_reason_or_an_amount_of_the_last_line():
    cells = ["Total remitted 1,800.00 AUD", "INV25-1000001", "02.01.2025", "1,000.00", "1,000.00",
             "INV25-1000002", "03.01.2025", "800.00", "800.00", "TOTAL REMITTED", "1,800.00"]
    advice = read_cells(cells, "pdf", "x.pdf", None, ref="1000")
    assert lines(advice)[1] == ("INV25-1000002", 80000, 0, None, 80000)


def test_the_subject_says_the_reference_in_the_word_with_digits(tmp_path):
    path = tmp_path / "advice.txt"
    path.write_text(MAIL.replace("Subject: Payment advice 250102632763",
                                 "Subject: Payment no. 250102632763 (Accounts Payable)"))
    assert parse_advice(path).payment_ref == "250102632763"


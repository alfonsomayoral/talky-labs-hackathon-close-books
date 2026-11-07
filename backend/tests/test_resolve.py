from __future__ import annotations

from types import SimpleNamespace

import polars as pl

from closebooks.cases import attach_questions, build_cases, overdue_cases
from closebooks.categories import fallback
from closebooks.model import Proposal, Row
from closebooks.policy import decide
from closebooks.resolve import resolve
from closebooks.state import OpenBalances


def txn(amount_cents: int, **kw):
    return {"bank_txn_id": "BT-1", "amount_cents": amount_cents, "currency": "EUR", "bank": "X", "bank_code": "",
            "bank_subcode": "", "text": "", **kw}


def test_receipt_without_evidence_is_unidentified_never_a_guess():
    out = fallback(txn(12697))
    assert (out.category, out.exception, out.rule) == ("UNIDENTIFIED", "UNIDENTIFIED", "FALLBACK-UNIDENTIFIED")


def test_debit_without_evidence_gets_a_category_and_no_exception():
    out = fallback(txn(-1500))
    assert out.category == "BANK_FEES"
    assert out.exception == ""
    assert out.rule == "FALLBACK-CATEGORY"


def test_balance_decreases_on_payment_and_reopens_on_return():
    b = OpenBalances({"ARI-1": 1000})
    b.apply("ARI-1", 400, "", "BT-1", "2025-01-01")
    assert b.open("ARI-1") == 600
    b.apply("ARI-1", 600, "", "BT-2", "2025-01-02")
    assert b.open("ARI-1") == 0
    b.apply("ARI-1", 1000, "RETURNED", "BT-3", "2025-01-03")
    assert b.open("ARI-1") == 1000
    assert [h["bankTxnId"] for h in b.history("ARI-1")] == ["BT-1", "BT-2", "BT-3"]


def test_duplicate_payment_does_not_move_the_balance():
    b = OpenBalances({"ARI-1": 0})
    b.apply("ARI-1", 1000, "DUPLICATE_PAYMENT", "BT-1", "2025-01-01")
    assert b.open("ARI-1") == 0


def line(open_cents, applied=None, *, item="API-1", item_currency="EUR", txn_currency="EUR", returned=False):
    return decide(item_id=item, item_currency=item_currency, txn_currency=txn_currency, open_cents=open_cents,
                  applied_cents=applied, returned=returned)


def test_payment_of_the_open_balance_clears_with_no_exception():
    assert line(1000) == (1000, "")
    assert line(1000, 1000) == (1000, "")


def test_payment_of_less_than_the_balance_is_partial_for_what_was_applied():
    assert line(1000, 400) == (400, "PARTIAL")


def test_invoice_paid_from_an_account_in_another_currency_is_fx_at_full_amount():
    assert line(1000, 1000, item_currency="USD", txn_currency="EUR") == (1000, "FX_DIFFERENCE")


def test_partial_keeps_its_code_and_credit_note_stays_empty_in_a_foreign_currency_line():
    assert line(1000, 400, item_currency="USD") == (400, "PARTIAL")
    assert line(1000, 1000, item="APC-1", item_currency="USD") == (1000, "")


def test_paying_an_item_already_settled_is_a_duplicate_of_what_was_paid_again():
    assert line(0, 1000) == (1000, "DUPLICATE_PAYMENT")


def test_returned_operation_reopens_the_amount_of_the_original_allocation():
    assert line(0, 1000, returned=True) == (1000, "RETURNED")


def _row(txn_id="BT-1", item="API-1", exception=None, rule="FILE-PAYMENT-RUN", confidence=1.0):
    return Row(txn_id, item, 1000, "EUR", None, exception, rule, confidence, party_id="S1")


TXNS = {"BT-1": {"bank_txn_id": "BT-1", "entity": "ES01", "booking_date": "2025-01-01", "amount_cents": -1000,
                 "currency": "EUR", "amount_eur_cents": -1000, "text": "X", "counterparty_name": None}}


def _case(rows):
    return build_cases(rows, TXNS, "now")


def test_line_closed_with_no_exception_opens_no_case():
    assert _case([_row()]) == []


def test_a_credit_note_paid_out_with_its_evidence_opens_no_case():
    assert _case([Row("BT-1", "ARC-1", 10000, "EUR", None, None, "CREDIT-PAYOUT", 1.0, "C1")]) == []


def test_supplier_invoice_paid_short_returned_or_twice_is_a_supplier_mismatch_to_write_about():
    for exception in ("PARTIAL", "RETURNED", "DUPLICATE_PAYMENT"):
        case = _case([_row(exception=exception)])[0]
        assert (case["kind"], case["suggestedAction"], case["status"]) == (
            "supplier_invoice_mismatch", "email_supplier", "auto")


def test_customer_exceptions_keep_their_own_kind():
    kinds = {"PARTIAL": "short_payment", "RETURNED": "returned", "DUPLICATE_PAYMENT": "duplicate_payment"}
    for exception, kind in kinds.items():
        assert _case([_row(item="ARI-1", exception=exception)])[0]["kind"] == kind


def test_fx_difference_is_shown_but_needs_nobody():
    case = _case([_row(exception="FX_DIFFERENCE")])[0]
    assert (case["kind"], case["status"], case["suggestedAction"]) == ("fx_difference", "auto", "none")


def test_low_confidence_needs_review_and_the_case_lists_every_item_of_the_line():
    case = _case([_row(item="ARI-1", exception="OVERPAYMENT", confidence=0.8), _row(item="ARI-2")])[0]
    assert case["status"] == "needs_review"
    assert case["itemIds"] == ["ARI-1", "ARI-2"]


def test_bulk_payment_opens_one_case_per_supplier_invoice_with_an_incident_at_its_amount():
    rows = [_row(item="API-1", exception="PARTIAL"), _row(item="API-2"), _row(item="API-3", exception="RETURNED")]
    rows[0].party_id, rows[2].party_id = "S1", "S3"
    cases = _case(rows)
    assert [(c["partyId"], c["itemIds"], c["amountCents"]) for c in cases] == [
        ("S1", ["API-1"], 1000), ("S3", ["API-3"], 1000)]
    assert len({c["caseId"] for c in cases}) == 2


def test_category_settled_with_evidence_opens_no_case():
    row = Row("BT-1", None, None, None, "BANK_FEES", None, "CAT-CODE", 1.0)
    assert _case([row]) == []


def test_amounts_of_a_case_are_magnitudes():
    case = _case([_row(exception="PARTIAL")])[0]
    assert (case["amountCents"], case["amountEur"]) == (1000, 1000)


def test_return_of_a_payment_made_before_the_data_starts_never_opens_more_than_the_total():
    b = OpenBalances({"ARI-1": 0}, totals={"ARI-1": 1000})
    b.apply("ARI-1", 1000, "RETURNED", "BT-1", "2025-01-01")
    assert b.open("ARI-1") == 1000
    b = OpenBalances({"ARI-2": 1000}, totals={"ARI-2": 1000})
    b.apply("ARI-2", 1000, "RETURNED", "BT-1", "2025-01-01")
    assert b.open("ARI-2") == 1000


def _customer_rows(rule, confidence, n, exception=None):
    return [Row("BT-1", f"ARI-{i}", 100, "EUR", None, exception, rule, confidence, party_id="C1") for i in range(n)]


def test_case_summary_describes_what_was_settled_without_rule_codes_and_only_fallbacks_say_no_match():
    settled = _case(_customer_rows("ADVICE-CSV", 0.8, 27))[0]["summary"]
    assert settled.endswith("27 facturas liquidadas por aviso de remesa") and "ADVICE" not in settled
    one = _case(_customer_rows("ADVICE-CSV", 0.8, 1))[0]["summary"]
    assert one.endswith("una factura liquidada por aviso de remesa")
    rows = _customer_rows("ADVICE-CSV", 1.0, 886)
    rows[0].exception = "SHORT_DISPUTE"
    rows[1].exception = rows[2].exception = "PARTIAL"
    cases = _case(rows)
    assert len(cases) == 3
    assert cases[0]["summary"].startswith("Factura con una parte disputada")
    assert cases[1]["summary"].startswith("Factura pagada en parte")
    fallback_row = Row("BT-1", None, None, None, "UNIDENTIFIED", "UNIDENTIFIED", "FALLBACK-UNIDENTIFIED", 0.0)
    assert "sin casación" in _case([fallback_row])[0]["summary"]


def test_dispute_and_short_payment_wait_for_a_person_even_at_full_confidence_but_a_return_does_not():
    for exception, status in (("SHORT_DISPUTE", "needs_review"), ("PARTIAL", "needs_review"), ("RETURNED", "auto"),
                              ("OVERPAYMENT", "auto")):
        case = _case([_row(item="ARI-1", exception=exception, rule="ADVICE-CSV")])[0]
        assert case["status"] == status, exception


def _invoice(item, party, due, cents, currency="EUR", entity="E1"):
    return {"item_id": item, "entity": entity, "party_id": party, "due_date": due, "currency": currency,
            "open_cents": cents}


def test_overdue_customer_adds_up_what_is_past_due_at_the_cutoff_per_customer_in_eur():
    items = [_invoice("ARI-1", "C1", "2025-01-10", 1000), _invoice("ARI-2", "C1", "2025-01-05", 500),
             _invoice("ARI-3", "C1", "2025-02-01", 9999),  # not due yet at the cutoff
             _invoice("ARI-4", "C1", "2024-12-01", 0),  # settled
             _invoice("ARI-5", "C2", "2025-01-01", 1100, "USD"), _invoice("ARI-6", "C2", None, 5000)]
    cases = overdue_cases(items, "2025-01-31", {"USD": 1.1}, {"C1": "Acme", "C2": "Beta"}, "now", {})
    assert [(c["caseId"], c["partyId"], c["itemIds"], c["amountEur"]) for c in cases] == [
        ("CASE-overdue_customer-1", "C1", ["ARI-2", "ARI-1"], 1500),
        ("CASE-overdue_customer-2", "C2", ["ARI-5"], 1000)]
    first = cases[0]
    assert (first["kind"], first["suggestedAction"], first["bankTxnId"], first["currency"], first["amountCents"],
            first["bookingDate"]) == ("overdue_customer", "email_customer", None, "EUR", 1500, "2025-01-31")
    assert "Acme" in first["summary"] and "2 facturas vencidas" in first["summary"]


def test_overdue_customer_keeps_the_biggest_per_entity(monkeypatch):
    monkeypatch.setattr("closebooks.cases.MAX_OVERDUE_PER_ENTITY", 2)
    items = [_invoice(f"ARI-{n}", f"C{n}", "2025-01-01", n * 100, entity="E1" if n < 5 else "E2") for n in range(1, 7)]
    kept = [c["partyId"] for c in overdue_cases(items, "2025-02-01", {}, {}, "now", {})]
    assert kept == ["C6", "C5", "C4", "C3"]  # E1: C4, C3 of C1..C4; E2: C6, C5


def _abstention(reason="subsets"):
    return {"BT-1": {"reason": reason, "options": [
        {"partyId": "C1", "items": [("ARI-1", 100), ("ARI-2", 200)]}, {"partyId": "C1", "items": [("ARI-3", 300)]}]}}


INFO = {f"ARI-{n}": {"number": f"FV{n}", "party_name": "Acme", "due_date": "2025-01-01", "currency": "EUR"}
        for n in (1, 2, 3)}
TXN = {**TXNS["BT-1"], "amount_cents": 300, "amount_eur_cents": 300, "counterparty_name": "ACME SL"}


def _fallback_case():
    row = Row("BT-1", None, None, None, "UNIDENTIFIED", "UNIDENTIFIED", "FALLBACK-UNIDENTIFIED", 0.0)
    return build_cases([row], {"BT-1": TXN}, "now")


def test_an_abstention_becomes_a_question_with_its_options_and_turns_its_case_into_a_question_case():
    cases = _fallback_case()
    questions = attach_questions(cases, _abstention(), {"BT-1": TXN}, lambda ids: INFO, {"C1": "Acme"}, "now")
    q = questions[0]
    assert (q["questionId"], q["caseId"], q["defaultOption"], q["status"]) == ("Q-000001", "CASE-BT-1", "none", "open")
    assert [o["id"] for o in q["options"]] == ["ARI-1+ARI-2", "ARI-3", "none"]
    assert q["options"][0]["label"] == "FV1 + FV2 · 3,00 EUR · Acme"
    assert q["rulePreview"]["kind"] == "payer_is_customer" and q["rulePreview"]["payerName"] == "ACME SL"
    assert (cases[0]["kind"], cases[0]["status"], cases[0]["questionId"]) == ("ambiguous_match", "question", "Q-000001")


def test_a_party_question_offers_the_parties():
    options = {"BT-1": {"reason": "parties", "options": [{"partyId": "C1", "items": [("ARI-1", 100)]},
                                                         {"partyId": "C2", "items": [("ARI-2", 100)]}]}}
    names = {"C1": "Acme", "C2": "Beta"}
    q = attach_questions(_fallback_case(), options, {"BT-1": TXN}, lambda ids: INFO, names, "now")[0]
    assert [o["id"] for o in q["options"]] == ["C1", "C2", "none"] and q["question"].startswith("¿De qué cliente")


def test_a_party_option_names_only_the_first_invoices():
    ids = [f"ARI-{n}" for n in range(1, 6)]
    info = {i: {**INFO["ARI-1"], "number": f"FV{i[-1]}"} for i in ids}
    options = {"BT-1": {"reason": "parties", "options": [{"partyId": "C1", "items": [(i, 100) for i in ids]}]}}
    q = attach_questions(_fallback_case(), options, {"BT-1": TXN}, lambda _: info, {"C1": "Acme"}, "now")[0]
    assert q["options"][0]["label"] == "Acme · FV1, FV2, FV3 y 2 más · 5,00 EUR"


def test_every_question_with_a_counterparty_previews_its_rule_by_name_or_by_account():
    options = _abstention()
    by_name = attach_questions(_fallback_case(), options, {"BT-1": TXN}, lambda _: INFO, {}, "now")[0]["rulePreview"]
    assert by_name["payerName"] == "ACME SL" and "iban" not in by_name and "cobros de ACME SL" in by_name["description"]
    nameless = {**TXN, "counterparty_name": None, "counterparty_account": "ES9100"}
    p = attach_questions(_fallback_case(), options, {"BT-1": nameless}, lambda _: INFO, {}, "now")[0]["rulePreview"]
    assert p["iban"] == "ES9100" and "payerName" not in p and p["partyId"] == "<la opción elegida>"
    debit = {**nameless, "amount_cents": -300, "amount_eur_cents": -300}
    p = attach_questions(_fallback_case(), options, {"BT-1": debit}, lambda _: INFO, {}, "now")[0]["rulePreview"]
    assert p["kind"] == "payer_is_customer" and "pagos a ES9100" in p["description"]
    bare = {**TXN, "counterparty_name": None}
    q = attach_questions(_fallback_case(), options, {"BT-1": bare}, lambda _: INFO, {}, "now")[0]
    assert q["rulePreview"] is None


def test_a_combined_option_reads_with_documents_nets_credit_notes_and_names_the_party():
    info = {"ARI-1": {"number": "FV1", "party_name": "Acme", "due_date": None, "currency": "EUR"},
            "ARC-1": {"number": "AB1", "party_name": "Acme", "due_date": None, "currency": "EUR"}}
    options = {"BT-1": {"reason": "subsets", "options": [
        {"partyId": "C9", "items": [("ARC-1", 100), ("ARI-1", 400)]}, {"partyId": "C9", "items": [("ARI-1", 300)]}]}}
    q = attach_questions(_fallback_case(), options, {"BT-1": TXN}, lambda _: info, {}, "now")[0]
    combined = next(o for o in q["options"] if "+" in o["id"])
    assert combined == {"id": "ARC-1+ARI-1", "label": "AB1 + FV1 · 3,00 EUR · Acme"}


def test_questions_are_capped_by_amount(monkeypatch):
    monkeypatch.setattr("closebooks.cases.MAX_QUESTIONS", 1)
    rows = [Row(t, None, None, None, "UNIDENTIFIED", "UNIDENTIFIED", "FALLBACK-UNIDENTIFIED", 0.0)
            for t in ("BT-1", "BT-2")]
    txns = {"BT-1": TXN, "BT-2": {**TXN, "bank_txn_id": "BT-2", "amount_eur_cents": 900}}
    found = {**_abstention(), "BT-2": _abstention()["BT-1"]}
    questions = attach_questions(build_cases(rows, txns, "now"), found, txns, lambda ids: INFO, {}, "now")
    assert [q["bankTxnId"] for q in questions] == ["BT-2"]


def test_customer_dispute_and_short_payment_open_one_case_per_invoice_to_review():
    rows = [_row(item="ARI-1", exception="SHORT_DISPUTE"), _row(item="ARI-2"), _row(item="ARI-3", exception="PARTIAL")]
    cases = _case(rows)
    assert [(c["kind"], c["itemIds"], c["status"], c["amountCents"]) for c in cases] == [
        ("dispute", ["ARI-1"], "needs_review", 1000), ("short_payment", ["ARI-3"], "needs_review", 1000)]
    assert len({c["caseId"] for c in cases}) == 2


def _overdue(**kw):
    item_ = {"item_id": "ARI-1", "entity": "E1", "party_id": "C1", "due_date": "2025-06-01", "currency": "EUR",
             "open_cents": 1000}
    return overdue_cases([item_], "2025-06-30", {"EUR": 1.0}, {"C1": "Cliente"}, "now", **kw)


def test_overdue_customer_goes_to_review_for_invoices_more_than_15_days_past_due():
    case = _overdue(last_movement={})[0]
    assert (case["status"], case["amountEur"]) == ("needs_review", 1000)
    late = {"item_id": "ARI-2", "entity": "E1", "party_id": "C2", "due_date": "2025-06-20", "currency": "EUR",
            "open_cents": 1000}
    assert overdue_cases([late], "2025-06-30", {"EUR": 1.0}, {}, "now", last_movement={}) == []


def test_customer_who_paid_in_the_last_30_days_is_not_overdue_it_is_probably_our_unmatched_payment():
    assert _overdue(last_movement={"C1": "2025-06-10"}) == []
    assert len(_overdue(last_movement={"C1": "2025-05-20"})) == 1


def test_paying_again_what_an_uncited_rule_settled_is_not_a_duplicate_but_the_first_real_payment():
    items = pl.DataFrame({"item_id": ["ARI-1"], "open_cents": [1000], "total_cents": [1000], "currency": ["EUR"],
                          "party_id": ["C1"], "payment_terms": ["T30"], "issue_date": ["2025-01-01"]})
    masters = {"payment_terms": pl.DataFrame({"code": ["T30"], "early_payment_discount_pct": [None],
                                              "discount_days": [None]},
                                             schema_overrides={"early_payment_discount_pct": pl.String,
                                                               "discount_days": pl.String}),
               "customers": pl.DataFrame({"customer_id": ["C1"], "country": ["ES"]})}
    ids = ["BT-1", "BT-2", "BT-3"]
    n = len(ids)
    t = pl.DataFrame({"bank_txn_id": ids, "booking_date": ["2025-01-01", "2025-01-02", "2025-01-03"],
                      "amount_cents": [1000] * n, "currency": ["EUR"] * n, "bank": ["B"] * n, "bank_code": [""] * n,
                      "bank_subcode": [""] * n, "text": ["X"] * n, "orig_cents": [None] * n,
                      "orig_currency": [None] * n, "amount_eur_cents": [1000] * n, "entity": ["E1"] * n,
                      "counterparty_name": [None] * n, "counterparty_account": [None] * n,
                      "remittance_info": [None] * n,
                      "ref1": [None] * n, "ref2": [None] * n, "end_to_end_id": [None] * n},
                     schema_overrides={c: pl.String for c in ("orig_currency", "counterparty_name",
                                                              "counterparty_account", "remittance_info", "ref1", "ref2",
                                                              "end_to_end_id")} | {"orig_cents": pl.Int64})
    proposals = {"BT-1": Proposal("PARTY-AMOUNT", [("ARI-1", None)], by_cash=True),
                 "BT-2": Proposal("REF-TEXT", [("ARI-1", None)], by_cash=True),
                 "BT-3": Proposal("REF-TEXT", [("ARI-1", None)], by_cash=True)}
    rows, _ = resolve(SimpleNamespace(items=items, txns=t, masters=masters), proposals)
    assert [r.exception for r in rows] == [None, None, "DUPLICATE_PAYMENT"]
    # BT-2025-0165470: no citation the second time either, so nothing says the first match was the wrong one.
    proposals = {"BT-1": Proposal("PARTY-AMOUNT", [("ARI-1", None)], by_cash=True),
                 "BT-2": Proposal("PARTY-DUPLICATE", [("ARI-1", None)], by_cash=True),
                 "BT-3": Proposal("REF-TEXT", [("ARI-1", None)], by_cash=True)}
    rows, _ = resolve(SimpleNamespace(items=items, txns=t, masters=masters), proposals)
    assert [r.exception for r in rows][:2] == [None, "DUPLICATE_PAYMENT"]


def test_cash_short_of_an_advice_leaves_its_last_printed_line_partial_with_the_advice_as_evidence():
    items = pl.DataFrame({"item_id": ["ARI-OLD", "ARI-NEW"], "open_cents": [1000, 1000], "total_cents": [1000, 1000],
                          "currency": ["EUR", "EUR"], "party_id": ["C1", "C1"], "payment_terms": ["T30", "T30"],
                          "issue_date": ["2025-01-01", "2025-02-01"]})
    masters = {"payment_terms": pl.DataFrame({"code": ["T30"], "early_payment_discount_pct": [None],
                                              "discount_days": [None]},
                                             schema_overrides={"early_payment_discount_pct": pl.String,
                                                               "discount_days": pl.String}),
               "customers": pl.DataFrame({"customer_id": ["C1"], "country": ["ES"]})}
    t = pl.DataFrame({"bank_txn_id": ["BT-1"], "booking_date": ["2025-03-01"], "amount_cents": [1500],
                      "currency": ["EUR"], "bank": ["B"], "bank_code": [""], "bank_subcode": [""], "text": ["X"],
                      "orig_cents": [None], "orig_currency": [None], "amount_eur_cents": [1500], "entity": ["E1"],
                      "counterparty_name": [None], "counterparty_account": [None], "remittance_info": [None],
                      "ref1": [None], "ref2": [None], "end_to_end_id": [None]},
                     schema_overrides={c: pl.String for c in ("orig_currency", "counterparty_name",
                                                              "counterparty_account", "remittance_info", "ref1", "ref2",
                                                              "end_to_end_id")} | {"orig_cents": pl.Int64})
    source = {"kind": "remittanceAdvice", "ref": "remittance_advices/E1/RA_a.txt", "label": "REF"}
    proposal = Proposal("ADVICE-TXT", [("ARI-NEW", None), ("ARI-OLD", None)], by_cash=True, in_listed_order=True,
                        sources=[source])
    rows, _ = resolve(SimpleNamespace(items=items, txns=t, masters=masters), {"BT-1": proposal})
    assert [(r.item_id, r.amount_cents, r.exception) for r in rows] == [("ARI-NEW", 1000, None),
                                                                        ("ARI-OLD", 500, "PARTIAL")]
    assert rows[1].sources == [source]


def test_cancelled_invoice_paid_by_a_file_with_nothing_before_is_not_a_duplicate():
    # BT-2025-0009286: the lockbox lists an invoice cancelled by a credit note; it opens at 0 but was never paid.
    items = pl.DataFrame({"item_id": ["ARI-1", "ARC-1"], "item_type": ["ARI", "ARC"], "entity": ["E1", "E1"],
                          "document_number": ["F1", "A1"], "related_document": [None, "F1"],
                          "reason": [None, "Anulación de factura"], "open_cents": [0, 0], "total_cents": [1000, 1000],
                          "currency": ["EUR", "EUR"], "party_id": ["C1", "C1"], "payment_terms": ["T30", None],
                          "issue_date": ["2025-01-01", "2025-01-01"]})
    masters = {"payment_terms": pl.DataFrame({"code": ["T30"], "early_payment_discount_pct": [None],
                                              "discount_days": [None]},
                                             schema_overrides={"early_payment_discount_pct": pl.String,
                                                               "discount_days": pl.String}),
               "customers": pl.DataFrame({"customer_id": ["C1"], "country": ["ES"]})}
    t = pl.DataFrame({"bank_txn_id": ["BT-1"], "booking_date": ["2025-01-02"], "amount_cents": [1000],
                      "currency": ["EUR"], "bank": ["B"], "bank_code": [""], "bank_subcode": [""], "text": ["X"],
                      "orig_cents": [None], "orig_currency": [None], "amount_eur_cents": [1000], "entity": ["E1"],
                      "counterparty_name": [None], "counterparty_account": [None], "remittance_info": [None],
                      "ref1": [None], "ref2": [None], "end_to_end_id": [None]},
                     schema_overrides={c: pl.String for c in ("orig_currency", "counterparty_name",
                                                              "counterparty_account", "remittance_info", "ref1", "ref2",
                                                              "end_to_end_id")} | {"orig_cents": pl.Int64})
    proposals = {"BT-1": Proposal("FILE-CHEQUE", [("ARI-1", 1000)])}
    rows, _ = resolve(SimpleNamespace(items=items, txns=t, masters=masters), proposals)
    assert (rows[0].amount_cents, rows[0].exception) == (1000, None)


def _plan_rows(cash, opening, amounts):
    items = pl.DataFrame({"item_id": ["ARI-1"], "open_cents": [opening], "total_cents": [sum(amounts)],
                          "currency": ["EUR"], "party_id": ["C1"], "payment_terms": ["T30"],
                          "issue_date": ["2025-01-01"]})
    masters = {"payment_terms": pl.DataFrame({"code": ["T30"], "early_payment_discount_pct": [None],
                                              "discount_days": [None]},
                                             schema_overrides={"early_payment_discount_pct": pl.String,
                                                               "discount_days": pl.String}),
               "customers": pl.DataFrame({"customer_id": ["C1"], "country": ["ES"]})}
    t = pl.DataFrame({"bank_txn_id": ["BT-1"], "booking_date": ["2025-01-02"], "amount_cents": [cash],
                      "currency": ["EUR"], "bank": ["B"], "bank_code": [""], "bank_subcode": [""], "text": ["X"],
                      "orig_cents": [None], "orig_currency": [None], "amount_eur_cents": [cash], "entity": ["E1"],
                      "counterparty_name": [None], "counterparty_account": [None], "remittance_info": [None],
                      "ref1": [None], "ref2": [None], "end_to_end_id": [None]},
                     schema_overrides={c: pl.String for c in ("orig_currency", "counterparty_name",
                                                              "counterparty_account", "remittance_info", "ref1", "ref2",
                                                              "end_to_end_id")} | {"orig_cents": pl.Int64})

    class Plan:
        clauses = {"ARI-1": {"instalments": {"amounts": amounts}}}

        def __call__(self, txn, balances):
            return Proposal("REF-TEXT", [("ARI-1", None)], by_cash=True)

    rows, _ = resolve(SimpleNamespace(items=items, txns=t, masters=masters), {}, Plan())
    return rows[0]


def test_last_instalment_of_a_plan_has_no_exception_even_if_an_earlier_one_was_not_seen():
    # POLICIES §3: FV24 at 3 instalments, the first ones missed by the engine: the balance alone would say PARTIAL.
    row = _plan_rows(30000, 100000, [50000, 20000, 30000])
    assert (row.amount_cents, row.exception) == (30000, None)


def test_an_instalment_that_is_not_the_last_is_partial_even_if_it_clears_the_balance():
    row = _plan_rows(20000, 20000, [50000, 20000, 30000])
    assert (row.amount_cents, row.exception) == (20000, "PARTIAL")


def test_equal_instalments_do_not_say_which_one_this_is():
    assert _plan_rows(20000, 20000, [20000, 20000]).exception is None
    assert _plan_rows(20000, 40000, [20000, 20000]).exception == "PARTIAL"

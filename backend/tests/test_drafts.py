"""Plantillas deterministas de borradores: ningún modelo, ninguna dirección inventada."""
from __future__ import annotations

from closebooks.drafts import DRAFTS_PER_KIND, language_of, money, render, template_of, top_per_template


def case(kind="overdue_customer", **extra):
    return {"caseId": "CASE-1", "kind": kind, "partyId": "C1", "entity": "ES01", "amountCents": 123456,
            "currency": "EUR", "amountEur": 123456, "bookingDate": "2025-01-31", **extra}


def facts(country="ES", n=2):
    return {"partyName": "Acme", "country": country, "email": None, "sender": "Valtermia Ibérica, S.A.U.",
            "items": [{"number": f"FV{i}", "due_date": f"2025-01-0{i}", "currency": "EUR", "open_cents": 1000 * i}
                      for i in range(1, n + 1)]}


def test_overdue_claim_lists_the_invoices_and_signs_with_the_entity_and_invents_no_address():
    d = render(case(), facts())
    assert d["kind"] == "email_customer" and d["generatedBy"] == "template" and d["status"] == "draft"
    assert d["to"] is None and d["toName"] == "Acme" and d["language"] == "es"
    assert "1.234,56 EUR" in d["body"] and "- FV1 · vence 2025-01-01 · 10,00 EUR" in d["body"]
    assert d["body"].endswith("Valtermia Ibérica, S.A.U.")


def test_every_kind_has_its_own_text_and_the_supplier_ones_are_for_suppliers():
    subjects = {}
    for kind, exception in (("overdue_customer", None), ("duplicate_payment", None), ("dispute", None),
                            ("overpayment", None), ("supplier_invoice_mismatch", None),
                            ("supplier_invoice_mismatch", "DUPLICATE_PAYMENT"), ("supplier_credit_pending", None)):
        d = render(case(kind), facts(), exception)
        subjects[(kind, exception)] = d["subject"]
        assert d["kind"] == ("email_supplier" if kind.startswith("supplier") else "email_customer")
    assert len(set(subjects.values())) == 7
    assert render(case("returned"), facts()) is None and render(case(partyId=None), facts()) is None


def test_language_follows_the_country_of_the_party_and_amounts_follow_the_language():
    assert [language_of(c) for c in ("FR", "DE", "IT", "PT", "GB", "ES", "MX", None, "ZZ")] == [
        "fr", "de", "it", "pt", "en", "es", "es", "es", "es"]
    assert money(123456, "EUR", "en") == "1,234.56 EUR" and money(123456, "EUR", "fr") == "1 234,56 EUR"
    english = render(case(), facts("GB"))
    assert english["language"] == "en" and english["body"].startswith("Dear Acme,")
    assert "1,234.56 EUR" in english["body"]
    assert render(case(), facts("DE"))["body"].startswith("Sehr geehrte")


def test_a_dispute_lists_only_the_invoices_still_open():
    its = facts()["items"]
    its[0]["open_cents"] = 0
    body = render(case("dispute"), {**facts(), "items": its})["body"]
    assert "FV1" not in body and "- FV2 · vence 2025-01-02 · 20,00 EUR" in body


def test_long_lists_are_cut_and_say_how_many_more():
    body = render(case(), facts(n=20))["body"]
    assert body.count("\n- ") == 13 and "… y 8 más" in body


def test_only_the_biggest_cases_of_each_template_get_a_draft_in_a_stable_order():
    cases = [case(caseId=f"CASE-{n}", amountEur=n) for n in range(DRAFTS_PER_KIND + 5)]
    cases.append(case("dispute", caseId="CASE-D", amountEur=1))
    cases.append(case("overdue_customer", caseId="CASE-X", partyId=None))
    chosen = [c["caseId"] for c in top_per_template(cases, {})]
    assert len(chosen) == DRAFTS_PER_KIND + 1 and "CASE-0" not in chosen and "CASE-X" not in chosen
    assert chosen[0] == "CASE-D" and chosen[1] == f"CASE-{DRAFTS_PER_KIND + 4}"
    duplicate = template_of(case("supplier_invoice_mismatch"), "DUPLICATE_PAYMENT")
    assert duplicate == ("email_supplier", "duplicate_supplier")

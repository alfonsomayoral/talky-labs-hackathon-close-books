"""Tercero + partidas abiertas en ese momento + números citados. Textos reales de TRAIN."""
from __future__ import annotations

from types import SimpleNamespace

import polars as pl

from closebooks.rules.parties import PartyIndex, normalize
from closebooks.rules.party_amount import PartyAmount
from closebooks.state import OpenBalances


def masters(customers=(), suppliers=()):
    cols = ["customer_id", "entity", "name", "trade_name", "iban", "group_id", "parent_customer_id", "sepa_mandate_id"]
    sup = ["supplier_id", "entity", "name", "iban"]
    return {
        "customers": pl.DataFrame([dict(zip(cols, c, strict=True)) for c in customers],
                                  schema=dict.fromkeys(cols, pl.String)),
        "suppliers": pl.DataFrame([dict(zip(sup, s, strict=True)) for s in suppliers],
                                  schema=dict.fromkeys(sup, pl.String)),
    }


def item(item_id, party, number, cents, issued="2024-01-01", open_cents=None, name=None, po=None, currency="EUR",
         entity="E1"):
    return {"item_id": item_id, "item_type": item_id[:3], "entity": entity, "party_id": party,
            "party_name": name or party,
            "document_number": number, "issue_date": issued, "currency": currency, "total_cents": cents,
            "open_cents": cents if open_cents is None else open_cents, "customer_po": po}


def engine(items, customers=(("C1", "E1", "Wellness Garrido S.L.", None, "ES11", None, None, None),), suppliers=()):
    table = pl.DataFrame(items, schema_overrides={"customer_po": pl.String})
    phase = SimpleNamespace(items=table, masters=masters(customers, suppliers), start="2021-01-01")
    balances = OpenBalances(dict(zip(table["item_id"], table["open_cents"], strict=True)))
    return PartyAmount(phase, reserved=set()), balances


def txn(amount, text="", name=None, remit=None, iban=None, date="2024-06-01", entity="E1", currency="EUR", orig=None,
        orig_ccy=None):
    return {"bank_txn_id": "BT-1", "entity": entity, "booking_date": date, "amount_cents": amount, "currency": currency,
            "text": text, "counterparty_name": name, "remittance_info": remit, "counterparty_account": iban,
            "ref1": None, "ref2": None, "end_to_end_id": None, "orig_cents": orig, "orig_currency": orig_ccy}


def lines(proposal):
    return {i for i, _ in proposal.lines} if proposal else None


def test_normalize_drops_accents_and_case():
    assert normalize("Rodríguez Climatización S.L.") == "RODRIGUEZ CLIMATIZACION S L"


def test_party_from_counterparty_name_exact():
    index = PartyIndex(masters([("C1", "E1", "Rubio Aguas S.A.", None, None, None, None, None)]), pl.DataFrame(
        schema=dict.fromkeys(["entity", "party_id", "party_name"], pl.String)))
    assert index.find(txn(1, name="Rubio Aguas S.A."), "customer") == ["C1"]


def test_party_from_a_name_cut_and_split_across_n43_fields():
    index = PartyIndex(masters([("C1", "E1", "Construcciones Lomaseca S.L.", None, None, None, None, None),
                                ("C2", "E1", "Otra Empresa S.L.", None, None, None, None, None)]),
                       pl.DataFrame(schema=dict.fromkeys(["entity", "party_id", "party_name"], pl.String)))
    assert index.find(txn(1, "TRANSFERENCIA DE CONSTRUCCIONES LOMASE | CA S.L."), "customer") == ["C1"]


def test_party_from_the_paying_iban():
    index = PartyIndex(masters([("C1", "E1", "Alfa", None, "ES7712", None, None, None)]),
                       pl.DataFrame(schema=dict.fromkeys(["entity", "party_id", "party_name"], pl.String)))
    assert index.find(txn(1, "TRANSF", iban="ES7712"), "customer") == ["C1"]


def test_party_in_another_entity_is_not_found():
    index = PartyIndex(masters([("C1", "E2", "Rubio Aguas S.A.", None, None, None, None, None)]),
                       pl.DataFrame(schema=dict.fromkeys(["entity", "party_id", "party_name"], pl.String)))
    assert index.find(txn(1, name="Rubio Aguas S.A."), "customer") == []


NAME = "TRANSFERENCIA DE WELLNESS GARRIDO S.L. | "


def test_receipt_with_no_party_is_never_matched_even_with_the_exact_amount_of_an_invoice():
    rule, balances = engine([item("ARI-1", "C1", "FV23-0111433", 149401)])
    assert rule(txn(149401, "INGRESO EN EFECTIVO"), balances) is None


def test_single_open_invoice_of_the_party_with_the_exact_amount():
    rule, balances = engine([item("ARI-1", "C1", "FV23-0311283", 124088), item("ARI-2", "C1", "FV23-1", 5)])
    proposal = rule(txn(124088, NAME), balances)
    assert lines(proposal) == {"ARI-1"}
    assert proposal.rule == "PARTY-AMOUNT"


def test_same_amount_several_open_goes_to_the_oldest_open():
    rule, balances = engine([item("ARI-2", "C1", "F2", 1000, "2024-03-01"),
                             item("ARI-1", "C1", "F1", 1000, "2024-02-01")])
    assert lines(rule(txn(1000, NAME), balances)) == {"ARI-1"}
    balances.apply("ARI-1", 1000, "", "BT-0", "2024-05-01")
    assert lines(rule(txn(1000, NAME), balances)) == {"ARI-2"}


def test_invoice_issued_after_the_payment_is_not_a_candidate():
    rule, balances = engine([item("ARI-1", "C1", "F1", 1000, "2024-07-01")])
    assert rule(txn(1000, NAME), balances) is None


def test_cited_number_cut_or_without_prefix_within_the_party_settles_the_cited_invoices():
    rule, balances = engine([item("ARI-1", "C1", "1062410577", 547647), item("ARI-2", "C1", "1062413148", 1479971),
                             item("ARI-3", "C1", "1062499999", 1000)])
    proposal = rule(txn(2027618, NAME, remit="INVOICE 1062410577 413148"), balances)
    assert lines(proposal) == {"ARI-1", "ARI-2"}
    assert proposal.rule.startswith("REF-")


def test_two_invoices_summing_to_the_cash_with_no_citation():
    rule, balances = engine([item("ARI-1", "C1", "F1", 49385), item("ARI-2", "C1", "F2", 189668),
                             item("ARI-3", "C1", "F3", 7)])
    assert lines(rule(txn(239053, NAME), balances)) == {"ARI-1", "ARI-2"}


def test_invoices_minus_credit_note_summing_to_the_cash():
    rule, balances = engine([item("ARI-1", "C1", "F1", 616632), item("ARC-1", "C1", "A1", 308316)])
    assert lines(rule(txn(308316, NAME), balances)) == {"ARI-1", "ARC-1"}


def test_two_different_subsets_with_the_same_sum_are_not_guessed():
    rule, balances = engine([item("ARI-1", "C1", "F1", 300), item("ARI-2", "C1", "F2", 700),
                             item("ARI-3", "C1", "F3", 400), item("ARI-4", "C1", "F4", 600)])
    assert rule(txn(1000, NAME), balances) is None


def test_discounted_payment_of_a_single_invoice_with_no_citation():
    rule, balances = engine([item("ARI-1", "C1", "F1", 140394)])
    rule.terms_pct = {"ARI-1": 2.0}
    proposal = rule(txn(137586, NAME), balances)
    assert lines(proposal) == {"ARI-1"}
    assert proposal.by_cash


def test_invoice_already_settled_and_cited_again_is_proposed_for_the_duplicate():
    rule, balances = engine([item("ARI-1", "C1", "FV21-0300659", 2881173, open_cents=0)])
    assert lines(rule(txn(2881173, NAME, remit="FRAS FV21-0300659"), balances)) == {"ARI-1"}


def test_foreign_payment_is_compared_in_the_currency_of_the_invoice():
    rule, balances = engine([item("ARI-1", "C1", "F1", 100000, currency="USD")])
    assert lines(rule(txn(92000, NAME, orig=100000, orig_ccy="USD"), balances)) == {"ARI-1"}


def test_invoice_reserved_by_a_document_rule_is_not_eaten_by_an_uncited_payment():
    rule, balances = engine([item("ARI-1", "C1", "FV1234", 1000)])
    rule.reserved = {"ARI-1"}
    assert rule(txn(1000, NAME), balances) is None
    assert lines(rule(txn(1000, NAME, remit="FRA FV1234"), balances)) == {"ARI-1"}


def test_item_older_than_train_and_never_cited_has_no_known_state_and_is_not_a_candidate():
    rule, balances = engine([item("ARI-1", "C1", "FV1234", 1000, "2020-12-01")])
    rule.unknown_before = "2021-01-01"
    assert rule(txn(1000, NAME), balances) is None
    assert lines(rule(txn(1000, NAME, remit="FRA FV1234"), balances)) == {"ARI-1"}


def test_debit_without_file_matches_the_supplier_invoice():
    rule, balances = engine([item("API-1", "S1", "F21/03076", 80135)], customers=(),
                            suppliers=(("S1", "E1", "Metalurgica Express", None),))
    debit = txn(-80135, "SEPA-LASTSCHRIFT MREF+33 SVWZ+RECIBO F21/03076", name="Metalurgica Express")
    assert lines(rule(debit, balances)) == {"API-1"}


def test_a_short_number_that_does_not_explain_the_cash_is_not_a_citation():
    # "REF 123" must not pull in an invoice ending in 123 of another amount.
    rule, balances = engine([item("ARI-1", "C1", "FV23-0100123", 5000), item("ARI-2", "C1", "FV23-0100777", 700)])
    assert lines(rule(txn(700, NAME, remit="REF 123"), balances)) == {"ARI-2"}


def test_a_short_number_that_explains_the_cash_is_a_citation():
    rule, balances = engine([item("ARI-1", "C1", "FV23-0100123", 5000), item("ARI-2", "C1", "FV23-0100124", 5000)])
    assert lines(rule(txn(5000, NAME, remit="FRA 124"), balances)) == {"ARI-2"}


def test_a_cut_number_matching_several_invoices_keeps_those_that_add_up():
    # "FV23-011 FV23-011": real, the bank cut the numbers.
    rule, balances = engine([item("ARI-1", "C1", "FV23-0111433", 149401), item("ARI-2", "C1", "FV23-0114377", 160845),
                             item("ARI-3", "C1", "FV23-0119999", 777)])
    assert lines(rule(txn(310246, NAME, remit="FRA. FV23-011 FV23-011"), balances)) == {"ARI-1", "ARI-2"}


def test_cited_invoice_completed_with_the_open_ones_that_add_up_to_the_cash():
    rule, balances = engine([item("ARI-1", "C1", "FV22-0110337", 1000), item("ARI-2", "C1", "FV22-0108438", 500),
                             item("ARI-3", "C1", "FV22-0100001", 77)])
    assert lines(rule(txn(1500, NAME, remit="FACTURA FV22-0110337"), balances)) == {"ARI-1", "ARI-2"}


def test_full_number_cited_explains_a_partial_payment():
    rule, balances = engine([item("ARI-1", "C1", "FV23-0111433", 1000), item("ARI-2", "C1", "FV23-0111434", 2000)])
    proposal = rule(txn(400, NAME, remit="A CUENTA FV23-0111433"), balances)
    assert lines(proposal) == {"ARI-1"}
    assert proposal.by_cash


def test_big_pool_still_finds_up_to_four_items_if_they_are_the_only_ones():
    items = [item(f"ARI-{i}", "C1", f"F{i}", 1000003 * (i + 1) + i * i * 7919) for i in range(30)]
    rule, balances = engine(items)
    chosen = items[3:4] + items[11:12] + items[20:21]
    target = sum(i["total_cents"] for i in chosen)
    found = rule._subset([((i["item_id"], "", "", "", 0, "", ""), i["total_cents"]) for i in items], target)
    assert found is None or set(found) == {i["item_id"] for i in chosen}


def _index(*names):
    rows = [(f"C{i}", "E1", n, None, None, None, None, None) for i, n in enumerate(names)]
    printed = pl.DataFrame(schema=dict.fromkeys(["entity", "party_id", "party_name"], pl.String))
    return PartyIndex(masters(rows), printed)


def test_unknown_ordering_party_is_not_taken_for_a_customer_with_a_similar_name():
    # Real forced match: "Hydro Evans Hermanos Inc." paid and there is only "Hydro Evans LLC" in the master.
    moved = txn(1, "ACH CREDIT HYDRO EVANS HERM CCD PAYMENT ID:259", name="Hydro Evans Hermanos Inc.")
    assert _index("Hydro Evans LLC").find(moved, "customer") == []


def test_unknown_ordering_party_still_finds_the_whole_name_of_who_it_pays_for():
    moved = txn(1, "CONFIRMING PENALARA ORD. RUBIO AGUAS S.A.", name="Confirming Penalara")
    assert _index("Rubio Aguas S.A.").find(moved, "customer") == ["C0"]


def test_uncited_small_shortfall_outside_sepa_is_found_for_the_only_invoice_it_fits():
    rule, balances = engine([item("ARI-1", "C1", "FV1234", 2556975), item("ARI-2", "C1", "FV1235", 9000)],
                            customers=(("C1", "E1", "Wellness Garrido S.L.", None, None, None, None, None),))
    rule.countries = {"C1": "CA"}
    plain = rule(txn(2553275, NAME), balances)
    assert plain is None  # an ordinary transfer that is merely close to an invoice stays unidentified
    wire = txn(2553275, NAME) | {"bank_code": "PMNT/RCDT/XBCT"}
    proposal = rule(wire, balances)
    assert lines(proposal) == {"ARI-1"}
    assert proposal.by_cash


def test_more_than_four_invoices_add_up_to_the_cash():
    items = [item(f"ARI-{i}", "C1", f"F{i}", c, f"2024-01-{i + 1:02d}")
             for i, c in enumerate((1009, 2017, 4001, 8009, 16001, 32003, 64007))]
    rule, balances = engine(items)
    assert lines(rule(txn(1009 + 4001 + 16001 + 32003 + 64007, NAME), balances)) == {
        "ARI-0", "ARI-2", "ARI-4", "ARI-5", "ARI-6"}


def test_oldest_invoices_in_a_row_add_up_with_more_candidates_than_the_search_pool():
    items = [item(f"ARI-{i:03d}", "C1", f"F{i}", 1000 + i, "2024-01-01") for i in range(60)]
    rule, balances = engine(items)
    assert lines(rule(txn(sum(1000 + i for i in range(30)), NAME), balances)) == {f"ARI-{i:03d}" for i in range(30)}


def test_number_cited_whole_settles_with_no_recognisable_party_if_the_amount_agrees():
    # "FP KING & MOORE BACKY INV INV25-0108533": the name is cut by the field.
    rule, balances = engine([item("ARI-1", "C9", "INV25-0108533", 5000)])
    assert lines(rule(txn(5000, "FP KING AND MOORE BACK INV INV25-0108533"), balances)) == {"ARI-1"}


def test_number_cited_whole_with_an_amount_far_from_it_and_no_party_is_not_settled():
    rule, balances = engine([item("ARI-1", "C9", "INV25-0108533", 5000)])
    assert rule(txn(900, "FP KING AND MOORE BACK INV INV25-0108533"), balances) is None


def test_cancelled_invoice_is_never_a_candidate_and_its_replacement_takes_the_citation():
    rule, balances = engine([item("ARI-1", "C1", "FV25-0100001", 5000), item("ARI-2", "C1", "FV25-0100002", 5000)])
    rule.cancelled, rule.clauses = {"ARI-1"}, {"ARI-2": {"replaces": {"replaces": "FV25-0100001"}}}
    rule.reindex()
    assert lines(rule(txn(5000, NAME, remit="FRA FV25-0100001"), balances)) == {"ARI-2"}


def test_month_in_the_text_picks_the_invoice_of_that_service_month_among_equal_amounts():
    rule, balances = engine([item("ARI-1", "C1", "F1", 1000, "2025-05-01"),
                             item("ARI-2", "C1", "F2", 1000, "2025-06-01")])
    assert lines(rule(txn(1000, NAME + "MANT. MAYO 25", date="2025-07-01"), balances)) == {"ARI-2"}


def test_month_from_the_pdf_wins_over_the_issue_date():
    rule, balances = engine([item("ARI-1", "C1", "F1", 1000, "2025-05-01"),
                             item("ARI-2", "C1", "F2", 1000, "2025-06-01")])
    rule.clauses = {"ARI-1": {"service_month": {"month": 5, "year": 2025}}}
    assert lines(rule(txn(1000, NAME + "SERVICE MAY 2025", date="2025-07-01"), balances)) == {"ARI-1"}


def test_no_month_keeps_fifo_among_equal_amounts():
    rule, balances = engine([item("ARI-1", "C1", "F1", 1000, "2025-05-01"),
                             item("ARI-2", "C1", "F2", 1000, "2025-06-01")])
    assert lines(rule(txn(1000, NAME, date="2025-07-01"), balances)) == {"ARI-1"}


def test_instalment_from_the_plan_of_the_pdf():
    rule, balances = engine([item("ARI-1", "C1", "F1", 30000), item("ARI-2", "C1", "F2", 50000)])
    rule.clauses = {"ARI-2": {"instalments": {"amounts": [20000, 15000, 15000]}}}
    proposal = rule(txn(15000, NAME), balances)
    assert lines(proposal) == {"ARI-2"}
    assert proposal.by_cash


def test_payment_net_of_retention_or_advance_from_the_pdf():
    rule, balances = engine([item("ARI-1", "C1", "F1", 30000), item("ARI-2", "C1", "F2", 50000)])
    rule.clauses = {"ARI-2": {"retention": {"payableCents": 45000}}}
    assert lines(rule(txn(45000, NAME), balances)) == {"ARI-2"}
    rule.clauses = {"ARI-1": {"advance_deduction": {"netDueCents": 21000}}}
    assert lines(rule(txn(21000, NAME), balances)) == {"ARI-1"}


def test_amount_that_nothing_explains_is_not_guessed_even_with_a_known_party():
    # Measured on the holdout: guessing a partial was right 12 % of the time, an overpayment 22 %, a duplicate 77 %.
    rule, balances = engine([item("ARI-1", "C1", "F1", 75407)])
    assert rule(txn(40000, NAME), balances) is None
    assert rule(txn(80407, NAME), balances) is None
    rule, balances = engine([item("ARI-1", "C1", "F1", 228043, open_cents=0)])
    assert rule(txn(228043, NAME), balances) is None


def test_debit_citing_a_customer_invoice_is_not_settled_by_the_number_alone():
    # customer_refund: we pay a refund and the text cites the invoice; that is a category, not a settlement.
    rule, balances = engine([item("ARI-1", "C9", "INV25-0108533", 5000)])
    assert rule(txn(-5000, "REFUND INV25-0108533"), balances) is None


def test_name_cut_in_the_middle_of_a_word_by_the_field_identifies_the_party():
    index = _index("Plasticos Express S.L.")
    assert index.find(txn(1, "PLASTICOS EXPRES | RECIBO 2025/00044"), "customer") == ["C0"]


def test_name_without_its_legal_form_identifies_the_party():
    moved = txn(1, "TRANSFERENCIAS HIDROTECNIA LOMASECA REF")
    assert _index("Hidrotecnia Lomaseca S.L.").find(moved, "customer") == ["C0"]

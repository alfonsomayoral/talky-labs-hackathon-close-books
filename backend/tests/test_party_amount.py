"""Tercero + partidas abiertas en ese momento + números citados. Textos reales de TRAIN."""
from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest

from closebooks.resolve import resolve
from closebooks.rules.parties import PartyIndex, normalize
from closebooks.rules.party_amount import PartyAmount, _chance
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
         entity="E1", related=None):
    return {"item_id": item_id, "item_type": item_id[:3], "entity": entity, "party_id": party,
            "party_name": name or party,
            "document_number": number, "issue_date": issued, "currency": currency, "total_cents": cents,
            "open_cents": cents if open_cents is None else open_cents, "customer_po": po, "related_document": related}


def engine(items, customers=(("C1", "E1", "Wellness Garrido S.L.", None, "ES11", None, None, None),), suppliers=()):
    table = pl.DataFrame(items, schema_overrides={"customer_po": pl.String, "related_document": pl.String})
    phase = SimpleNamespace(items=table, masters=masters(customers, suppliers), start="2021-01-01")
    balances = OpenBalances(dict(zip(table["item_id"], table["open_cents"], strict=True)))
    return PartyAmount(phase, reserved={}), balances


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
    rule.reserved = {"ARI-1": {"BT-0"}}
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


def test_outgoing_transfer_settles_the_cited_customer_credit_note():
    rule, balances = engine([item("ARC-1", "C1", "AV24-000001", 10000)])
    found = rule(txn(-10000, name="Wellness Garrido S.L.", remit="AV24-000001"), balances)
    assert lines(found) == {"ARC-1"}
    assert found.rule == "CREDIT-PAYOUT"
    assert found.lines == [("ARC-1", 10000)]


def test_customer_credit_note_payout_can_be_supported_by_its_pdf():
    rule, balances = engine([item("ARC-1", "C1", "AV24-000001", 10000)])
    rule.clauses = {"ARC-1": {"rappel_payout": {}}}
    assert lines(rule(txn(-10000, name="Wellness Garrido S.L."), balances)) == {"ARC-1"}


@pytest.mark.parametrize("variation", ["no_evidence", "short", "closed", "future", "foreign", "offset", "reserved",
                                          "uncertain", "ambiguous"])
def test_credit_note_payout_rejects_missing_or_ambiguous_evidence(variation):
    note = item("ARC-1", "C1", "AV24-000001", 10000,
                open_cents=0 if variation == "closed" else 10000,
                issued="2024-07-01" if variation == "future" else "2024-01-01",
                currency="USD" if variation == "foreign" else "EUR")
    notes = [note] + ([item("ARC-2", "C1", "AV24-000002", 10000)] if variation == "ambiguous" else [])
    rule, balances = engine(notes)
    if variation in ("offset", "ambiguous"):
        clause = "rappel_offset" if variation == "offset" else "rappel_payout"
        rule.clauses = {n["item_id"]: {clause: {}} for n in notes}
    if variation == "reserved":
        rule.reserved = {"ARC-1": {"BT-0"}}
    remit = None if variation in ("no_evidence", "ambiguous") else "AV24-000001"
    wire = txn(-9900 if variation == "short" else -10000, "WELLNESS GARR" if variation == "uncertain" else "",
               name=None if variation == "uncertain" else "Wellness Garrido S.L.", remit=remit)
    assert rule(wire, balances) is None


def test_credit_note_payout_resolves_to_its_whole_balance_with_no_exception():
    rule, _ = engine([item("ARC-1", "C1", "AV24-000001", 10000)])
    wire = txn(-10000, name="Wellness Garrido S.L.", remit="AV24-000001")
    book = masters(customers=(("C1", "E1", "Wellness Garrido S.L.", None, None, None, None, None),))
    book["customers"] = book["customers"].with_columns(pl.lit("ES").alias("country"))
    book["payment_terms"] = pl.DataFrame(schema=dict.fromkeys(
        ["code", "early_payment_discount_pct", "discount_days"], pl.String))
    phase = SimpleNamespace(items=rule._known.with_columns(pl.lit(None, pl.String).alias("payment_terms")),
                            masters=book, txns=pl.DataFrame([dict(wire, bank="B", bank_code="", bank_subcode="",
                                                                amount_eur_cents=wire["amount_cents"])],
                                                           schema_overrides={"orig_cents": pl.Int64}))
    rows, balances = resolve(phase, {}, rule)
    assert [(r.item_id, r.amount_cents, r.exception) for r in rows] == [("ARC-1", 10000, None)]
    assert balances.open("ARC-1") == 0


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


def test_the_space_after_a_whole_name_does_not_make_a_longer_name_win():
    # "S.L." is whole here; "S.L.U." only gets further by the space after the word. Both are real customers: abstain.
    moved = txn(1, "TRANSF. A SU FAVOR | 75081474-MOLINOS ARRAYAN S.L. | PLAZO 4/4")
    index = _index("Molinos Arrayan S.L.", "Molinos Arrayan S.L.U.")
    assert index.find(moved, "customer") == ["C0", "C1"]
    assert not index.certain


def test_a_whole_name_beats_a_longer_one_the_bank_would_have_cut_mid_name():
    moved = txn(1, "TRANSF. 75081474-MOLINOS ARRAYAN S.L.")
    index = _index("Molinos Arrayan S.L.", "Molinos Arrayan S.L. Export")
    assert index.find(moved, "customer") == ["C0"]
    assert index.certain


def test_a_customer_with_its_legal_form_cut_by_the_bank_is_still_found_but_not_certain():
    moved = txn(1, "TRANSF. A SU FAVOR | MOLINOS ARRAYAN S.L. | PLAZO 4/4")
    index = _index("Molinos Arrayan S.L.U.")
    assert index.find(moved, "customer") == ["C0"]
    assert not index.certain


def test_the_longer_name_written_whole_wins_over_the_shorter_one():
    moved = txn(1, "TRANSF. A SU FAVOR | MOLINOS ARRAYAN S.L.U. | PLAZO 4/4")
    index = _index("Molinos Arrayan S.L.", "Molinos Arrayan S.L.U.")
    assert index.find(moved, "customer") == ["C1"]
    assert index.certain


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


RIEGOS = (("C1", "E1", "Riegos Mar S.L.", None, "ES11", None, None, None),)


def test_a_month_word_of_the_party_name_without_a_year_is_not_a_month():
    rule, balances = engine([item("ARI-1", "C1", "F1", 1000, "2024-02-01"),
                             item("ARI-2", "C1", "F2", 1000, "2024-04-01")], customers=RIEGOS)
    assert lines(rule(txn(1000, "TRANSFERENCIA DE RIEGOS MAR S.L.", date="2024-07-01"), balances)) == {"ARI-1"}


def test_the_same_word_with_a_year_after_the_party_name_is_the_month():
    rule, balances = engine([item("ARI-1", "C1", "F1", 1000, "2024-02-01"),
                             item("ARI-2", "C1", "F2", 1000, "2024-04-01")], customers=RIEGOS)
    assert lines(rule(txn(1000, "RIEGOS MAR MAR 24", date="2024-07-01"), balances)) == {"ARI-2"}


def test_a_month_word_outside_the_party_name_is_the_month_without_a_year():
    rule, balances = engine([item("ARI-1", "C1", "F1", 1000, "2024-02-01"),
                             item("ARI-2", "C1", "F2", 1000, "2024-04-01")])
    assert lines(rule(txn(1000, NAME + "MANT. MAR", date="2024-07-01"), balances)) == {"ARI-2"}


def test_instalment_from_the_plan_of_the_pdf():
    rule, balances = engine([item("ARI-1", "C1", "F1", 30000), item("ARI-2", "C1", "F2", 50000)])
    rule.clauses = {"ARI-2": {"instalments": {"amounts": [20000, 15000, 15000]}}}
    proposal = rule(txn(15000, NAME), balances)
    assert lines(proposal) == {"ARI-2"}
    assert proposal.by_cash


def test_payment_net_of_retention_or_advance_from_the_pdf():
    rule, balances = engine([item("ARI-1", "C1", "F1", 30000), item("ARI-2", "C1", "F2", 50000)])
    rule.clauses = {"ARI-2": {"retention": {"pct": 10}}}
    assert lines(rule(txn(45000, NAME), balances)) == {"ARI-2"}
    rule.clauses = {"ARI-1": {"advance_deduction": {"netDueCents": 21000}}}
    assert lines(rule(txn(21000, NAME), balances)) == {"ARI-1"}


def test_amount_that_nothing_explains_is_not_guessed_even_with_a_known_party():
    # Measured on the holdout: guessing a partial was right 12 % of the time, an overpayment 22 %.
    rule, balances = engine([item("ARI-1", "C1", "F1", 75407)])
    assert rule(txn(40000, NAME), balances) is None
    assert rule(txn(80407, NAME), balances) is None


def settled(*rows):
    """An engine where these items were settled by an earlier line of this run."""
    rule, balances = engine(list(rows))
    for row in rows:
        balances.apply(row["item_id"], row["total_cents"], "", "BT-0", "2024-05-01")
    return rule, balances


def test_exact_total_of_the_one_invoice_of_the_party_already_settled_is_a_duplicate():
    # BT-2025-0080327: paid twice with no reference. Nothing is open for that amount and only one closed item has it.
    rule, balances = settled(item("ARI-1", "C1", "F1", 228043))
    found = rule(txn(228043, NAME), balances)
    assert found.rule == "PARTY-DUPLICATE" and lines(found) == {"ARI-1"}


def test_invoice_closed_before_this_run_may_just_look_like_the_cash():
    # BT-2025-0162197, unidentified_lookalike: nothing in the run says this invoice was ever paid.
    rule, balances = engine([item("ARI-1", "C1", "F1", 228043, open_cents=0)])
    assert rule(txn(228043, NAME), balances) is None


def test_two_settled_invoices_with_that_total_are_not_guessed():
    rule, balances = settled(item("ARI-1", "C1", "F1", 228043), item("ARI-2", "C1", "F2", 228043))
    assert rule(txn(228043, NAME), balances) is None


def test_settled_credit_note_of_that_amount_is_not_a_duplicate():
    rule, balances = settled(item("ARC-1", "C1", "A1", 228043))
    assert rule(txn(228043, NAME), balances) is None


def test_duplicate_needs_a_whole_party_name():
    rule, balances = settled(item("ARI-1", "C1", "F1", 228043))
    assert rule(txn(228043, "WELLNESS GARRIDO"), balances) is None


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


def test_invoices_bigger_than_the_cash_do_not_use_up_the_search():
    big = [item(f"ARI-B{i}", "C1", f"B{i}", 9000000 + i, f"2024-01-{(i % 27) + 1:02d}") for i in range(40)]
    wanted = [item("ARI-1", "C1", "F1", 1173527, "2024-02-01"), item("ARI-2", "C1", "F2", 1708759, "2024-03-01")]
    rule, balances = engine(big + wanted)
    assert lines(rule(txn(2882286, NAME), balances)) == {"ARI-1", "ARI-2"}


def test_cited_invoices_net_of_a_credit_note_the_text_does_not_cite():
    # ar_1toN_credit_note: the customer pays invoices minus a credit note and cites only the invoices.
    rule, balances = engine([item("ARI-1", "C1", "FV22-0110337", 10000), item("ARI-2", "C1", "FV22-0111165", 5000),
                             item("ARC-1", "C1", "AB22-0100001", 3000), item("ARC-2", "C1", "AB22-0100002", 777)])
    proposal = rule(txn(12000, NAME, remit="FACTURA FV22-0110337 0111165"), balances)
    assert lines(proposal) == {"ARI-1", "ARI-2", "ARC-1"}


def test_a_long_cut_number_that_only_fits_one_invoice_explains_a_partial():
    # "FT FT22-01-269": FT22-01-26956 paid in part.
    rule, balances = engine([item("ARI-1", "C1", "FT22-01-26956", 113861), item("ARI-2", "C1", "FT22-01-30000", 999)])
    assert lines(rule(txn(68316, NAME, remit="CAUSALE FT FT22-01-269"), balances)) == {"ARI-1"}


def test_a_short_cut_number_that_fits_several_invoices_explains_nothing_on_its_own():
    # 683,16 would be 60 % of ARI-1, a round share that PARTY-FRACTION explains with no citation.
    rule, balances = engine([item("ARI-1", "C1", "FT22-01-26956", 113861), item("ARI-2", "C1", "FT22-01-26999", 999)])
    assert rule(txn(68000, NAME, remit="CAUSALE FT FT22-01-269"), balances) is None


def test_rows_of_a_completed_reference_come_in_a_stable_order():
    # The CSV must be byte-identical between runs (CONTRACT §3): sets iterate differently in each process.
    items = [item(f"ARI-{i}", "C1", f"FV22-010000{i}", 1000 + i) for i in range(4)] + [item("ARI-9", "C1", "F9", 7)]
    rule, balances = engine(items)
    remit = "FACTURA FV22-0100003 FV22-0100001 FV22-0100002"
    proposal = rule(txn(1001 + 1002 + 1003 + 1000, NAME, remit=remit), balances)
    assert [i for i, _ in proposal.lines] == sorted(i for i, _ in proposal.lines)


def test_two_combinations_with_the_same_total_leave_no_proposal_but_a_recorded_abstention():
    items = [item("ARI-1", "C1", "FV1", 10000), item("ARI-2", "C1", "FV2", 20000), item("ARI-3", "C1", "FV3", 15000),
             item("ARI-4", "C1", "FV4", 15000)]
    rule, balances = engine(items)
    assert rule(txn(30000, name="Wellness Garrido S.L."), balances) is None
    found = rule.abstentions["BT-1"]
    assert found["reason"] == "subsets"
    tied = sorted(sorted(i for i, _ in o["items"]) for o in found["options"])
    assert tied == [["ARI-1", "ARI-2"], ["ARI-3", "ARI-4"]]
    assert {o["partyId"] for o in found["options"]} == {"C1"}


def test_two_customers_with_the_same_evidence_leave_no_proposal_but_list_both_as_options():
    customers = (("C1", "E1", "Wellness Garrido S.L.", None, "ES11", None, None, None),
                 ("C2", "E1", "Wellness Garrido S.L.", None, "ES22", None, None, None))
    rule, balances = engine([item("ARI-1", "C1", "FV1", 30000), item("ARI-2", "C2", "FV2", 30000)], customers)
    assert rule(txn(30000, name="Wellness Garrido S.L."), balances) is None
    found = rule.abstentions["BT-1"]
    assert found["reason"] == "parties"
    assert {o["partyId"]: o["items"] for o in found["options"]} == {"C1": [("ARI-1", 30000)], "C2": [("ARI-2", 30000)]}


def test_a_clear_match_or_no_evidence_records_no_abstention():
    rule, balances = engine([item("ARI-1", "C1", "FV1", 30000), item("ARI-2", "C1", "FV2", 5000)])
    assert lines(rule(txn(30000, name="Wellness Garrido S.L."), balances)) == {"ARI-1"}
    assert rule(txn(777, name="Wellness Garrido S.L."), balances) is None
    assert rule.abstentions == {}


def test_subset_needs_a_party_known_for_certain_not_a_name_the_bank_cut():
    items = [item("ARI-1", "C1", "F1", 49385), item("ARI-2", "C1", "F2", 189668), item("ARI-3", "C1", "F3", 7)]
    rule, balances = engine(items)
    assert lines(rule(txn(239053, "TRANSFERENCIA DE WELLNESS GARRIDO S.L."), balances)) == {"ARI-1", "ARI-2"}
    assert rule(txn(239053, "ACH CREDIT WELLNESS GARR"), balances) is None


def test_exact_amount_with_a_cut_name_still_settles_a_single_invoice():
    rule, balances = engine([item("ARI-1", "C1", "F1", 49385)])
    assert lines(rule(txn(49385, "ACH CREDIT WELLNESS GARR"), balances)) == {"ARI-1"}


def _run(prefix, n, cents=1000, start=1):
    return [item(f"{prefix}{i:02d}", "C1", f"F{prefix}{i}", cents + 37 * i * i + i,
                 f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}") for i in range(start, start + n)]


def test_block_of_consecutive_invoices_adds_up_with_too_many_candidates_for_a_unique_subset():
    # Holdout: payments of many invoices are often a run of consecutive dates, not the oldest.
    items = _run("ARI-", 40)
    rule, balances = engine(items)
    wanted = items[10:18]
    assert lines(rule(txn(sum(i["total_cents"] for i in wanted), NAME), balances)) == {i["item_id"] for i in wanted}


def test_block_of_consecutive_invoices_net_of_a_credit_note():
    items = _run("ARI-", 40) + [item("ARC-1", "C1", "A1", 12345, "2024-02-20")]
    rule, balances = engine(items)
    wanted = items[10:18]
    amount = sum(i["total_cents"] for i in wanted) - 12345
    assert lines(rule(txn(amount, NAME), balances)) == {i["item_id"] for i in wanted} | {"ARC-1"}


def test_debit_of_a_group_treasury_finds_the_supplier_of_another_entity():
    # POLICIES §5.2: ES00 pays invoices of its subsidiaries.
    index = PartyIndex(masters((), (("S1", "E2", "Vila Consultoria S.A.", None),)), pl.DataFrame(
        schema=dict.fromkeys(["entity", "party_id", "party_name"], pl.String)))
    assert index.find(txn(-1, "VILA CONSULTORIA | Recibos varios", entity="E1"), "supplier") == ["S1"]
    assert not index.certain


def test_receipt_does_not_search_customers_of_another_entity():
    index = PartyIndex(masters((("C1", "E2", "Rubio Aguas S.A.", None, None, None, None, None),)), pl.DataFrame(
        schema=dict.fromkeys(["entity", "party_id", "party_name"], pl.String)))
    assert index.find(txn(1, "TRANSF RUBIO AGUAS S.A.", entity="E1"), "customer") == []


def test_a_long_legal_form_does_not_lose_the_party_to_a_namesake():
    # "Camping Arenal del Sur S.L.U." against "... S.L.": real, the wrong namesake won.
    index = _index("Camping Arenal del Sur S.L.U.", "Camping Arenal del Sur S.L.")
    moved = txn(1, "TRANSFERENCIAS CAMPING ARENAL DEL SUR | CAMPING AR PAGO PENDIENTE")
    assert index.find(moved, "customer") == ["C0", "C1"]
    assert _index("Parra y Velasco Depuracion S.A. de C.V.").find(
        txn(1, "SPEI CONCEPTO PARRA Y VELASCO DEPURACION PAGO"), "customer") == ["C0"]


def test_a_different_last_word_is_not_a_legal_form():
    assert _index("Parra y Velasco Jardines").find(txn(1, "SPEI PARRA Y VELASCO PAGO"), "customer") == []


def pay(rows, cash, name="Wellness Garrido S.L.", text=""):
    found_engine, balances = engine(rows)
    return found_engine(txn(cash, text=text, name=name), balances)


def ids(proposal):
    return sorted(i for i, _ in proposal.lines)


# Amounts of BT-2025-0000124 (CAU01000021): 25 invoices of 34 open, by date, leaving one out and no reference at all.
RUN = [("ARI-1", 606383), ("ARI-2", 48089), ("ARI-3", 87132), ("ARI-4", 172951), ("ARI-5", 733770), ("ARI-6", 107901),
       ("ARI-7", 34133), ("ARI-8", 301915)]
RUN_CASH = 48089 + 87132 + 172951 + 107901 + 34133


def open_run(*extra):
    """More open invoices than a whole search can tell apart: only the run can explain the cash."""
    older = [item(f"ARI-0{n:02d}", "C1", f"FV23-0{n:06d}", 100000 + n * 1000, issued="2023-01-01") for n in range(20)]
    run = [item(i, "C1", f"FV24-0{n:06d}", cents, issued=f"2024-01-{n + 1:02d}") for n, (i, cents) in enumerate(RUN)]
    return [*older, *run, *extra]


def test_run_of_invoices_by_date_leaving_one_out_settles_with_no_citation():
    found = pay(open_run(), RUN_CASH)
    assert found.rule == "PARTY-WINDOW"
    assert ids(found) == ["ARI-2", "ARI-3", "ARI-4", "ARI-6", "ARI-7"]


def test_run_net_of_one_credit_note_leaving_one_out():
    note = item("ARC-1", "C1", "CN1", 20028, issued="2023-12-01")
    found = pay(open_run(note), RUN_CASH - 20028)
    assert found.rule == "PARTY-WINDOW"
    assert ids(found) == ["ARC-1", "ARI-2", "ARI-3", "ARI-4", "ARI-6", "ARI-7"]


def test_two_runs_that_explain_the_cash_are_not_guessed():
    twins = [item(f"ARI-{n}", "C1", f"FV24-0{n:06d}", cents, issued=f"2024-02-{n + 1:02d}")
             for n, cents in enumerate((1700, 7000, 5000, 9000, 1700, 7000, 5000, 9000, 1700))]
    older = [item(f"ARI-0{n:02d}", "C1", f"FV23-0{n:06d}", 10000 + n * 1000, issued="2023-01-01") for n in range(20)]
    assert pay([*older, *twins], 1700 + 7000 + 9000 + 1700 + 5000) is None


def test_window_needs_a_whole_party_name():
    assert pay(open_run(), RUN_CASH, name=None, text="WELLNESS GARRIDO") is None


def test_invoices_cited_and_the_rest_of_their_run_when_the_text_was_cut():
    found = pay(open_run(), RUN_CASH, text="FRA FV24-0000001 FV24-0000002")
    assert found.rule == "REF-COMPLETED"
    assert ids(found) == ["ARI-2", "ARI-3", "ARI-4", "ARI-6", "ARI-7"]


def test_a_run_that_leaves_out_a_cited_invoice_is_not_the_answer():
    found = pay(open_run(), RUN_CASH, text="FRA FV24-0000004")
    assert found.rule == "REF-TEXT"
    assert ids(found) == ["ARI-5"]


def test_a_unique_set_among_twenty_open_invoices_settles():
    values = [1000003 + 7919 * 2 ** n % 999983 for n in range(20)]
    rows = [item(f"ARI-{n:02d}", "C1", f"N{n}", v, issued=f"2024-02-{n + 1:02d}") for n, v in enumerate(values)]
    found = pay(rows, values[1] + values[9] + values[14] + values[3] + values[17])
    assert found.rule == "PARTY-SUBSET"
    assert ids(found) == ["ARI-01", "ARI-03", "ARI-09", "ARI-14", "ARI-17"]


def test_a_unique_set_among_many_small_invoices_means_nothing_and_is_not_taken():
    # 2^17 sets over a sum of about 1 M cents. That only one adds up to this cash is no proof of anything.
    values = [40000 + (n ** 3 * 7919 + n * 104729) % 40000 for n in range(17)]
    rows = [item(f"ARI-{n:02d}", "C1", f"N{n}", v, issued=f"2024-02-{n + 1:02d}") for n, v in enumerate(values)]
    assert pay(rows, sum(values[n] for n in (0, 1, 2, 3, 4, 5, 6, 7, 11))) is None


def test_chance_of_a_set_grows_with_the_sets_searched_and_falls_with_the_cents_they_spread_over():
    assert _chance(10 ** 3, [10 ** 6] * 2) < _chance(10 ** 4, [10 ** 6] * 2)
    assert _chance(10 ** 4, [10 ** 7] * 2) < _chance(10 ** 4, [10 ** 6] * 2)


def test_a_run_among_too_many_open_invoices_is_not_taken():
    many = [item(f"ARI-{n:03d}", "C1", f"FV24-1{n:06d}", 1000 + n % 37, issued=f"2024-03-{n % 28 + 1:02d}")
            for n in range(70)]
    assert pay(many, 5000 + 5 * 3) is None


def test_invoice_reserved_by_a_batch_is_free_again_once_the_batch_returned_it():
    # BT-2025-0014588: direct debit returned, the customer then pays by transfer with no reference.
    rule, balances = engine([item("ARI-1", "C1", "F1", 75407)])
    rule.reserved = {"ARI-1": {"BT-0", "BT-00"}}
    assert rule(txn(75407, NAME), balances) is None
    balances.apply("ARI-1", 75407, "", "BT-0", "2024-05-01")
    assert rule(txn(75407, NAME), balances).rule == "PARTY-DUPLICATE"
    balances.apply("ARI-1", 75407, "RETURNED", "BT-00", "2024-05-10")
    assert lines(rule(txn(75407, NAME), balances)) == {"ARI-1"}


def test_invoice_of_a_returned_batch_stays_reserved_while_a_re_presentation_is_to_come():
    rule, balances = engine([item("ARI-1", "C1", "F1", 75407)])
    rule.reserved = {"ARI-1": {"BT-0", "BT-00", "BT-000"}}
    balances.apply("ARI-1", 75407, "", "BT-0", "2024-05-01")
    balances.apply("ARI-1", 75407, "RETURNED", "BT-00", "2024-05-10")
    assert rule(txn(75407, NAME), balances) is None


# BT-2025-0000058: eleven customers named the same in AU01. Another one's invoice starts like the cut number.
HOMONYMS = (("C1", "E1", "Hydro Port Ellery Pty Ltd", None, None, None, None, None),
            ("C2", "E1", "Hydro Port Ellery Pty Ltd", None, None, None, None, None))
HOMONYM = "DIRECT CREDIT HYDRO PORT ELLERY PT INV# INV24-0223"


def test_of_two_customers_named_the_same_the_one_whose_invoice_is_the_cash_settles():
    rule, balances = engine([item("ARI-1", "C1", "INV24-0223583", 171730), item("ARI-2", "C2", "INV24-0223999", 90000)],
                            customers=HOMONYMS)
    found = rule(txn(171730, HOMONYM, name="Hydro Port Ellery Pty Ltd"), balances)
    assert lines(found) == {"ARI-1"}
    assert found.party_id == "C1"
    assert [c["itemId"] for c in found.candidates] == ["ARI-2"]
    assert {"kind": "customer", "ref": "C2"} in found.sources


def test_customers_with_different_names_are_not_homonyms_even_if_one_has_the_cash():
    # The bank cut the name: both start the same, and the cut does not say which one paid.
    customers = (("C1", "E1", "Hydro Port Ellery Pty Ltd", None, None, None, None, None),
                 ("C2", "E1", "Hydro Port Ellery North Pty Ltd", None, None, None, None, None))
    rule, balances = engine([item("ARI-1", "C1", "INV24-0223583", 171730), item("ARI-2", "C2", "INV24-0223999", 90000)],
                            customers=customers)
    assert rule(txn(171730, "DIRECT CREDIT HYDRO PORT ELLE INV# INV24-0223"), balances) is None


def test_of_two_customers_named_the_same_both_with_the_cash_nothing_is_guessed():
    rule, balances = engine([item("ARI-1", "C1", "INV24-0223583", 171730),
                             item("ARI-2", "C2", "INV24-0223999", 171730)], customers=HOMONYMS)
    assert rule(txn(171730, HOMONYM, name="Hydro Port Ellery Pty Ltd"), balances) is None


def test_of_two_customers_named_the_same_a_citation_that_explains_nothing_settles_nothing():
    rule, balances = engine([item("ARI-1", "C1", "INV24-0223583", 80000), item("ARI-2", "C2", "INV24-0223999", 90000)],
                            customers=HOMONYMS)
    assert rule(txn(171730, HOMONYM, name="Hydro Port Ellery Pty Ltd"), balances) is None


def discounted(*rows):
    rule, balances = engine(list(rows))
    rule.terms_pct = {r["item_id"]: 2.0 for r in rows}
    rule.discount_days = {r["item_id"]: 10 for r in rows}
    return rule, balances


def test_several_invoices_each_net_of_its_discount_add_up_to_the_cash():
    # BT-2025-0000118: a customer takes its early-payment discount on every invoice it pays, with no citation.
    rule, balances = discounted(item("ARI-1", "C1", "F1", 100003, issued="2024-05-28"),
                                item("ARI-2", "C1", "F2", 50011, issued="2024-05-28"),
                                item("ARI-3", "C1", "F3", 700013, issued="2024-05-28"))
    found = rule(txn(98003 + 49011, NAME), balances)
    assert found.rule == "PARTY-NET-SUBSET" and lines(found) == {"ARI-1", "ARI-2"}


def test_invoices_out_of_terms_are_not_net_of_their_discount():
    rule, balances = discounted(item("ARI-1", "C1", "F1", 100003, issued="2024-01-01"),
                                item("ARI-2", "C1", "F2", 50011, issued="2024-01-01"))
    assert rule(txn(98003 + 49011, NAME), balances) is None


# POLICIES §5.1: BT-2025-0000873, the parent pays with its own name and the invoice is of a subsidiary.
GROUP = (("C1", "E1", "Holding Porto Alvor S.A.", None, None, "G1", None, None),
         ("C2", "E1", "Piscinas Porto Alvor Lda.", None, None, "G1", "C1", None),
         ("C3", "E1", "Jardins Porto Alvor Lda.", None, None, "G1", "C1", None))
PARENT = "TRANSFERENCIA DE HOLDING PORTO ALVOR S.A. | "


def test_parent_paying_the_only_invoice_of_its_group_with_that_amount():
    rule, balances = engine([item("ARI-1", "C2", "F1", 71939), item("ARI-2", "C3", "F2", 12000)], customers=GROUP)
    found = rule(txn(71939, PARENT), balances)
    assert found.party_id == "C2" and lines(found) == {"ARI-1"}
    assert {"kind": "customer", "ref": "C1"} in found.sources


def test_two_members_of_the_group_with_that_amount_are_not_guessed():
    rule, balances = engine([item("ARI-1", "C2", "F1", 71939), item("ARI-2", "C3", "F2", 71939)], customers=GROUP)
    assert rule(txn(71939, PARENT), balances) is None


def test_payer_with_its_own_invoice_of_that_amount_goes_first():
    rule, balances = engine([item("ARI-0", "C1", "F0", 71939), item("ARI-1", "C2", "F1", 71939)], customers=GROUP)
    assert lines(rule(txn(71939, PARENT), balances)) == {"ARI-0"}


def test_a_group_member_whose_invoices_do_not_add_up_to_the_cash_settles_nothing():
    rule, balances = engine([item("ARI-1", "C2", "F1", 71939)], customers=GROUP)
    assert rule(txn(50000, PARENT), balances) is None


def test_a_name_that_is_not_whole_does_not_reach_the_group():
    rule, balances = engine([item("ARI-1", "C2", "F1", 71939)], customers=GROUP)
    assert rule(txn(71939, "HOLDING PORTO"), balances) is None


# POLICIES §5.2: BT-2025-0002687, ES00 pays; the same supplier also exists in ES00 with nothing open.
FACTORY = (("S1", "E1", "Valvulas Castro S.L.", None), ("S2", "E2", "Valvulas Castro S.L.", None))


def test_payment_factory_settles_the_invoice_of_the_same_supplier_in_another_entity():
    rule, balances = engine([item("API-1", "S2", "500", 57297, entity="E2")], customers=(), suppliers=FACTORY)
    found = rule(txn(-57297, "ADEUDO A SU CARGO | VALVULAS CASTRO S.L. N 7039", entity="E1"), balances)
    assert found.party_id == "S2" and lines(found) == {"API-1"}
    assert found.sources == [{"kind": "supplier", "ref": "S2", "label": "paid from E1"}]


def test_payment_factory_with_two_entities_that_could_be_paid_is_not_guessed():
    suppliers = (*FACTORY, ("S3", "E3", "Valvulas Castro S.L.", None))
    rule, balances = engine([item("API-1", "S2", "500", 57297, entity="E2"),
                             item("API-2", "S3", "600", 57297, entity="E3")], customers=(), suppliers=suppliers)
    assert rule(txn(-57297, "ADEUDO A SU CARGO | VALVULAS CASTRO S.L. N 7039", entity="E1"), balances) is None


def test_payment_factory_does_not_apply_to_what_customers_pay():
    customers = (("C1", "E1", "Valvulas Castro S.L.", None, None, None, None, None),
                 ("C2", "E2", "Valvulas Castro S.L.", None, None, None, None, None))
    rule, balances = engine([item("ARI-1", "C2", "500", 57297, entity="E2")], customers=customers)
    assert rule(txn(57297, "TRANSFERENCIA DE VALVULAS CASTRO S.L.", entity="E1"), balances) is None


def test_a_round_fraction_of_the_only_open_invoice_it_fits_is_a_partial_payment():
    # BT-2025-0065845: 594,43 is 30 % of NF0125000182 (1.981,44), with the cent rounded.
    rule, balances = engine([item("ARI-1", "C1", "NF0125000182", 198144), item("ARI-2", "C1", "NF0125000183", 51000)])
    wire = txn(59443, NAME)
    proposal = rule(wire, balances)
    assert (proposal.rule, lines(proposal)) == ("PARTY-FRACTION", {"ARI-1"})
    book = masters(customers=(("C1", "E1", "Wellness Garrido S.L.", None, "ES11", None, None, None),))
    book["customers"] = book["customers"].with_columns(pl.lit("ES").alias("country"))
    book["payment_terms"] = pl.DataFrame(schema=dict.fromkeys(
        ["code", "early_payment_discount_pct", "discount_days"], pl.String))
    phase = SimpleNamespace(items=rule._known.with_columns(pl.lit(None, pl.String).alias("payment_terms")),
                            masters=book, txns=pl.DataFrame([dict(wire, bank="B", bank_code="", bank_subcode="",
                                                                amount_eur_cents=wire["amount_cents"])],
                                                           schema_overrides={"orig_cents": pl.Int64}))
    rows, balances = resolve(phase, {}, rule)
    assert [(r.item_id, r.amount_cents, r.exception) for r in rows] == [("ARI-1", 59443, "PARTIAL")]
    assert balances.open("ARI-1") == 198144 - 59443


def test_an_invoice_with_an_open_credit_note_of_its_own_is_not_taken_for_a_fraction():
    # Credit notes are often round fractions of their invoice: invoice minus note looks like a partial.
    rule, balances = engine([item("ARI-1", "C1", "NF0125000182", 198144),
                             item("ARC-1", "C1", "AB0125000007", 49536, related="NF0125000182")])
    assert rule(txn(59443, NAME), balances) is None


def test_a_fraction_that_two_open_invoices_fit_is_not_guessed():
    rule, balances = engine([item("ARI-1", "C1", "F1", 198144), item("ARI-2", "C1", "F2", 297216)])
    assert rule(txn(59443, NAME), balances) is None


def test_a_cash_that_is_no_round_fraction_of_the_invoice_is_not_a_partial():
    rule, balances = engine([item("ARI-1", "C1", "F1", 198144)])
    assert rule(txn(73908, NAME), balances) is None


def test_a_unique_round_fraction_among_many_open_invoices_means_nothing_and_is_not_taken():
    # A hundred invoices of about 600: each offers 19 shares within a cent, so one of them fitting proves nothing.
    many = [item(f"ARI-{n}", "C1", f"F{n}", 60001 + n) for n in range(100)]
    rule, balances = engine([*many, item("ARI-X", "C1", "NF0125000182", 198144)])
    assert rule(txn(59443, NAME), balances) is None

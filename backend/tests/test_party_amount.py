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
         entity="E1"):
    return {"item_id": item_id, "item_type": item_id[:3], "entity": entity, "party_id": party,
            "party_name": name or party,
            "document_number": number, "issue_date": issued, "currency": currency, "total_cents": cents,
            "open_cents": cents if open_cents is None else open_cents, "customer_po": po}


def engine(items, customers=(("C1", "E1", "Wellness Garrido S.L.", None, "ES11", None, None, None),), suppliers=()):
    table = pl.DataFrame(items, schema_overrides={"customer_po": pl.String})
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


def test_noisy_reference_yields_to_one_exact_invoice_of_a_certain_party():
    rule, balances = engine([item("ARI-1", "C1", "FV24-000001", 15000),
                             item("ARI-2", "C1", "FV24-000002", 10000)])
    found = rule(txn(10000, name="Wellness Garrido S.L.", remit="FV24-000001"), balances)
    assert lines(found) == {"ARI-2"}
    assert found.rule == "PARTY-REF-NOISE"


@pytest.mark.parametrize("cash,amounts", [(10000, [15000, 10000, 10000]), (10100, [10000, 10100])])
def test_ambiguous_alternative_or_explained_overpayment_keeps_the_reference(cash, amounts):
    rule, balances = engine([item(f"ARI-{n}", "C1", f"FV24-{n:06}", amount)
                             for n, amount in enumerate(amounts, 1)])
    assert lines(rule(txn(cash, name="Wellness Garrido S.L.", remit="FV24-000001"), balances)) == {"ARI-1"}


def test_noisy_reference_does_not_override_an_explained_discount_or_pdf_plan():
    rule, balances = engine([item("ARI-1", "C1", "FV24-000001", 10000),
                             item("ARI-2", "C1", "FV24-000002", 9800)])
    rule.terms_pct = {"ARI-1": 2.0}
    wire = txn(9800, name="Wellness Garrido S.L.", remit="FV24-000001")
    assert lines(rule(wire, balances)) == {"ARI-1"}
    rule.terms_pct = {}
    rule.clauses = {"ARI-1": {"instalments": {"amounts": [9800, 200]}}}
    assert lines(rule(wire, balances)) == {"ARI-1"}


def test_noisy_reference_is_not_overridden_from_a_truncated_party_name():
    rule, balances = engine([item("ARI-1", "C1", "FV24-000001", 15000),
                             item("ARI-2", "C1", "FV24-000002", 10000)])
    assert lines(rule(txn(10000, "WELLNESS GARR", remit="FV24-000001"), balances)) == {"ARI-1"}


@pytest.mark.parametrize("reason", ["A CUENTA", "PARTIAL PAYMENT", "INSTALMENT 2/6"])
def test_explicit_partial_keeps_its_reference_even_when_another_invoice_has_the_cash(reason):
    rule, balances = engine([item("ARI-1", "C1", "FV24-000001", 15000),
                             item("ARI-2", "C1", "FV24-000002", 10000)])
    wire = txn(10000, name="Wellness Garrido S.L.", remit=f"{reason} FV24-000001")
    assert lines(rule(wire, balances)) == {"ARI-1"}


@pytest.mark.parametrize("text", ["INSTALMENT 2/6", "PLAZO 2 DE 6", "PRESTAÇÃO 2/6", "ECHEANCE 2 SUR 6"])
def test_explicit_instalment_without_pdf_explains_a_unique_invoice(text):
    rule, balances = engine([item("ARI-1", "C1", "F1", 60000)])
    found = rule(txn(10000, name="Wellness Garrido S.L.", remit=text), balances)
    assert lines(found) == {"ARI-1"}
    assert found.rule == "PARTY-INSTALMENT"


@pytest.mark.parametrize("text", ["INSTALMENT 0/6", "INSTALMENT 7/6", "INSTALMENT 1/1", "REF 2/6",
                                      "INSTALMENT 2/6 AND PLAZO 2/3"])
def test_missing_invalid_or_conflicting_instalments_are_not_guessed(text):
    rule, balances = engine([item("ARI-1", "C1", "F1", 60000)])
    assert rule(txn(10000, name="Wellness Garrido S.L.", remit=text), balances) is None


def test_instalment_needs_unique_invoice_certain_party_and_no_contradicting_pdf():
    rule, balances = engine([item("ARI-1", "C1", "F1", 60000), item("ARI-2", "C1", "F2", 60000)])
    wire = txn(10000, name="Wellness Garrido S.L.", remit="INSTALMENT 2/6")
    assert rule(wire, balances) is None
    rule, balances = engine([item("ARI-1", "C1", "F1", 60000)])
    assert rule(txn(10000, "WELLNESS GARR", remit="INSTALMENT 2/6"), balances) is None
    rule.clauses = {"ARI-1": {"instalments": {"amounts": [30000, 30000]}}}
    assert rule(wire, balances) is None


def test_instalment_rounding_uses_cents_and_never_exceeds_the_open_balance():
    rule, balances = engine([item("ARI-1", "C1", "F1", 10000)])
    assert lines(rule(txn(3333, name="Wellness Garrido S.L.", remit="PLAZO 1/3"), balances)) == {"ARI-1"}
    balances.apply("ARI-1", 8000, "PARTIAL", "BT-0", "2024-05-01")
    assert rule(txn(3333, name="Wellness Garrido S.L.", remit="PLAZO 3/3"), balances) is None


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


@pytest.mark.parametrize("case", ["reference", "instalment", "credit"])
def test_new_evidence_rules_resolve_amount_exception_and_remaining_balance(case):
    if case == "reference":
        items = [item("ARI-1", "C1", "FV24-000001", 15000), item("ARI-2", "C1", "FV24-000002", 10000)]
        wire = txn(10000, name="Wellness Garrido S.L.", remit="FV24-000001")
        expected = ("ARI-2", 10000, None, 0)
    elif case == "instalment":
        items = [item("ARI-1", "C1", "FV24-000001", 60000)]
        wire = txn(10000, name="Wellness Garrido S.L.", remit="INSTALMENT 2/6")
        expected = ("ARI-1", 10000, "PARTIAL", 50000)
    else:
        items = [item("ARC-1", "C1", "AV24-000001", 10000)]
        wire = txn(-10000, name="Wellness Garrido S.L.", remit="AV24-000001")
        expected = ("ARC-1", 10000, None, 0)
    rule, _ = engine(items)
    book = masters(customers=(("C1", "E1", "Wellness Garrido S.L.", None, None, None, None, None),))
    book["customers"] = book["customers"].with_columns(pl.lit("ES").alias("country"))
    book["payment_terms"] = pl.DataFrame(schema=dict.fromkeys(
        ["code", "early_payment_discount_pct", "discount_days"], pl.String))
    phase = SimpleNamespace(items=rule._known.with_columns(pl.lit(None, pl.String).alias("payment_terms")),
                            masters=book, txns=pl.DataFrame([dict(wire, bank="B", bank_code="", bank_subcode="",
                                                                amount_eur_cents=wire["amount_cents"])],
                                                           schema_overrides={"orig_cents": pl.Int64}))
    rows, balances = resolve(phase, {}, rule)
    assert len(rows) == 1
    row = rows[0]
    assert (row.item_id, row.amount_cents, row.exception, balances.open(row.item_id)) == expected


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
    rule, balances = engine([item("ARI-1", "C1", "FT22-01-26956", 113861), item("ARI-2", "C1", "FT22-01-26999", 999)])
    assert rule(txn(68316, NAME, remit="CAUSALE FT FT22-01-269"), balances) is None


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

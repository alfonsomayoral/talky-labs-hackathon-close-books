"""POLICIES §2-§3, clause by clause. Amounts from real lines of sample/TRAIN where the comment says so."""
from __future__ import annotations

from closebooks.policy import (
    NODES,
    Evidence,
    Gap,
    Hypothesis,
    Terms,
    allocate,
    as_candidates,
    choose,
    cross_border,
    decide,
    fee_fits,
    fee_stated,
    search,
    weighed,
)

D2N30 = Terms(discount_pct=2.0, discount_days=10, issue_date="2025-06-01", total_cents=140394, country="ES")
PLAIN = Terms(discount_pct=None, discount_days=None, issue_date="2025-06-01", total_cents=100000, country="ES")


def line(open_cents, applied, deduction, *, terms=PLAIN, booked="2025-06-05", item="ARI-1", item_ccy="EUR",
         txn_ccy="EUR"):
    return decide(item, item_ccy, txn_ccy, open_cents, applied, deduction=deduction, terms=terms, booking_date=booked)


def test_discount_within_terms_clears_the_full_amount():
    # BT-2025-0162710: 1375.86 for 1403.94 (2 %).
    assert line(140394, 137586, (-2808, "DISCOUNT"), terms=D2N30) == (140394, "SHORT_DISCOUNT")


def test_discount_has_three_days_of_grace_counted_on_the_booking_date():
    last_day = "2025-06-14"  # issue + 10 + 3
    assert line(140394, 137586, (-2808, "DISCOUNT"), terms=D2N30, booked=last_day)[1] == "SHORT_DISCOUNT"
    assert line(140394, 137586, (-2808, "DISCOUNT"), terms=D2N30, booked="2025-06-15") == (137586, "PARTIAL")


def test_discount_claimed_with_no_discount_in_the_terms_is_partial():
    assert line(100000, 98000, (-2000, "DISCOUNT")) == (98000, "PARTIAL")


def test_withholding_clears_the_full_amount():
    assert line(100000, 90000, (-10000, "RET")) == (100000, "SHORT_WITHHOLDING")


def test_any_other_stated_reason_is_a_dispute_for_what_was_paid():
    for reason in ("PRICE DIFF", "DAMAGED GOODS", "PENAL. RETRASO", "LOGISTIC FEE", "UN MOTIVO NUEVO"):
        assert line(100000, 93000, (-7000, reason)) == (93000, "SHORT_DISPUTE")


def test_shortfall_with_no_reason_is_read_from_its_ratio():
    mexico = Terms(None, None, "2025-06-01", 100000, "MX")
    assert line(100000, 98750, (-1250, None), terms=mexico)[1] == "SHORT_WITHHOLDING"
    assert line(100000, 98500, (-1500, None), terms=mexico)[1] == "SHORT_WITHHOLDING"
    assert line(100000, 90000, (-10000, None), terms=mexico)[1] == "SHORT_WITHHOLDING"
    assert line(140394, 137586, (-2808, None), terms=D2N30)[1] == "SHORT_DISCOUNT"
    assert line(100000, 80000, (-20000, None)) == (80000, "PARTIAL")


def test_foreign_currency_replaces_a_full_clearing_exception_but_not_partial_or_dispute():
    assert line(100000, 90000, (-10000, "RET"), item_ccy="USD") == (100000, "FX_DIFFERENCE")
    assert line(100000, 93000, (-7000, "PRICE DIFF"), item_ccy="USD") == (93000, "SHORT_DISPUTE")
    assert line(100000, 80000, (-20000, None), item_ccy="USD") == (80000, "PARTIAL")


def facts(item, open_cents, terms=PLAIN):
    return (item, open_cents, terms)


def test_cash_equal_to_invoices_minus_credit_notes_clears_all_with_empty_credit_notes():
    out = allocate(70000, [facts("ARI-1", 100000), facts("ARC-1", 30000)], "2025-06-05", False)
    assert out == {"ARI-1": (100000, ""), "ARC-1": (30000, "")}


def test_cash_short_by_the_discount_of_each_invoice_in_terms():
    second = Terms(2.0, 10, "2025-06-01", 50000, "ES")
    out = allocate(137586 + 49000, [facts("ARI-1", 140394, D2N30), facts("ARI-2", 50000, second)], "2025-06-05", False)
    assert out == {"ARI-1": (140394, "SHORT_DISCOUNT"), "ARI-2": (50000, "SHORT_DISCOUNT")}


def test_discount_taken_late_stays_open_on_each_invoice():
    second = Terms(2.0, 10, "2025-06-01", 50000, "ES")
    out = allocate(137586 + 49000, [facts("ARI-1", 140394, D2N30), facts("ARI-2", 50000, second)], "2025-07-30", False)
    assert out == {"ARI-1": (137586, "PARTIAL"), "ARI-2": (49000, "PARTIAL")}


def test_withholding_at_source_only_for_customers_of_those_countries():
    br = Terms(None, None, "2025-06-01", 100000, "BR")
    out = allocate(90000, [facts("ARI-1", 100000, br)], "2025-06-05", False)
    assert out == {"ARI-1": (100000, "SHORT_WITHHOLDING")}
    assert allocate(90000, [facts("ARI-1", 100000)], "2025-06-05", False) == {"ARI-1": (90000, "PARTIAL")}


def test_small_shortfall_of_a_cross_border_transfer_is_bank_charges():
    ca = Terms(None, None, "2025-06-01", 2556975, "CA")  # 25532.75 for 25569.75: 37.00 of intermediary fee
    assert allocate(2553275, [facts("ARI-1", 2556975, ca)], "2025-06-05", False, eur_per_cent=1.0) == {
        "ARI-1": (2556975, "SHORT_BANK_CHARGES")}


def test_shortfall_over_the_fee_limits_or_inside_sepa_is_partial():
    ca = Terms(None, None, "2025-06-01", 2556975, "CA")
    over_60 = allocate(2556975 - 6001, [facts("ARI-1", 2556975, ca)], "2025-06-05", False, eur_per_cent=1.0)
    assert over_60["ARI-1"][1] == "PARTIAL"
    small = Terms(None, None, "2025-06-01", 100000, "CA")  # 30.00 is under 60 EUR but 3 % of the item
    out = allocate(97000, [facts("ARI-1", 100000, small)], "2025-06-05", False, eur_per_cent=1.0)
    assert out["ARI-1"][1] == "PARTIAL"
    es = Terms(None, None, "2025-06-01", 2556975, "ES")
    out = allocate(2553275, [facts("ARI-1", 2556975, es)], "2025-06-05", False, eur_per_cent=1.0)
    assert out["ARI-1"][1] == "PARTIAL"


def test_more_than_the_open_amount_of_a_single_invoice_is_overpayment_at_the_open_amount():
    assert allocate(76000, [facts("ARI-1", 75407)], "2025-06-05", False) == {"ARI-1": (75407, "OVERPAYMENT")}


def test_foreign_currency_full_payment_is_fx_on_invoices_and_empty_on_credit_notes():
    out = allocate(None, [facts("ARI-1", 100000), facts("ARC-1", 30000)], "2025-06-05", True)
    assert out == {"ARI-1": (100000, "FX_DIFFERENCE"), "ARC-1": (30000, "")}


def test_foreign_currency_partial_keeps_partial():
    assert allocate(40000, [facts("ARI-1", 100000)], "2025-06-05", True) == {"ARI-1": (40000, "PARTIAL")}


def test_item_with_nothing_open_paid_again_is_a_duplicate_of_what_was_paid():
    settled = Terms(None, None, "2025-01-01", 228043, "ES")
    assert allocate(228043, [facts("ARI-1", 0, settled)], "2025-06-05", False) == {
        "ARI-1": (228043, "DUPLICATE_PAYMENT")}


def test_partial_cash_on_several_invoices_goes_to_the_oldest_first():
    older = Terms(None, None, "2025-01-01", 100000, "ES")
    newer = Terms(None, None, "2025-03-01", 100000, "ES")
    out = allocate(150000, [facts("ARI-2", 100000, newer), facts("ARI-1", 100000, older)], "2025-06-05", False)
    assert out == {"ARI-1": (100000, ""), "ARI-2": (50000, "PARTIAL")}


def test_partial_cash_on_a_listing_fills_it_in_the_printed_order_not_by_age():
    first = Terms(None, None, "2025-03-01", 100000, "ES", listed_at=0)
    last = Terms(None, None, "2025-01-01", 100000, "ES", listed_at=1)
    out = allocate(150000, [facts("ARI-2", 100000, first), facts("ARI-1", 100000, last)], "2025-06-05", False)
    assert out == {"ARI-2": (100000, ""), "ARI-1": (50000, "PARTIAL")}


def test_a_gap_that_is_a_discount_stays_a_discount_even_on_a_listing():
    second = Terms(None, None, "2025-06-01", 50000, "ES", listed_at=1)
    listed = Terms(2.0, 10, "2025-06-01", 140394, "ES", listed_at=0)
    out = allocate(137586 + 50000, [facts("ARI-1", 140394, listed), facts("ARI-2", 50000, second)], "2025-06-05", False)
    assert out == {"ARI-1": (140394, "SHORT_DISCOUNT"), "ARI-2": (50000, "")}


def test_a_huge_excess_is_not_an_overpayment_of_that_invoice_but_an_incomplete_citation():
    # Real overpayments stay under 32 % of the invoice (p99 in the holdout); false ones have a median excess of x5.
    assert allocate(500000, [facts("ARI-1", 100000)], "2025-06-05", False) == {"ARI-1": (100000, "")}


def test_cross_border_signal_comes_from_the_iso_code_or_the_bank_text():
    assert cross_border("PMNT/RCDT/XBCT", "WIRE IN /ORG/LAKEVIEW")
    assert cross_border("13", "TRANSFER. EN DIV. | CDDJCBXX | GASTOS SHA")
    assert not cross_border("PMNT/RCDT/ESCT", "ACH CREDIT WATER CARE BLUE")


def test_a_fee_the_bank_states_is_a_cross_border_signal_even_on_a_plain_transfer_code():
    # Invented: a plain transfer code and the intermediary's fee printed by the bank (POLICIES §3).
    plain = "BONIFICO DA ACME AG CAUSALE F1"
    assert not cross_border("NTRF", plain)
    assert cross_border("NTRF", plain + " /CHGS/EUR45,00")


def test_a_stated_fee_only_explains_the_shortfall_of_its_amount_and_currency():
    stated = "BONIFICO DA ACME AG CAUSALE F1 /CHGS/EUR45,00"
    assert fee_fits(stated, "EUR", 4500)
    assert not fee_fits(stated, "EUR", 4501)
    assert not fee_fits(stated, "USD", 4500)
    assert fee_fits("TRANSFER. EN DIV. | GASTOS SHA", "EUR", 4501)  # no amount stated: only the limits can decide


def test_duplicate_needs_the_exact_amount_of_the_settled_item():
    settled = Terms(None, None, "2025-01-01", 100000, "ES")
    out = allocate(100000, [facts("ARI-1", 0, settled)], "2025-06-05", False)
    assert out == {"ARI-1": (100000, "DUPLICATE_PAYMENT")}
    assert allocate(40000, [facts("ARI-1", 0, settled)], "2025-06-05", False) == {"ARI-1": (40000, "")}
    assert line(0, 40000, None, terms=settled) == (40000, "")
    assert line(0, 100000, None, terms=settled) == (100000, "DUPLICATE_PAYMENT")


def test_overpayment_only_for_the_excess_real_ones_show():
    # Holdout: excess <= 2 % is 96.6 % right and exactly 10 % is a real pattern; else, an incomplete citation.
    assert allocate(101000, [facts("ARI-1", 100000)], "2025-06-05", False)["ARI-1"][1] == "OVERPAYMENT"
    assert allocate(110000, [facts("ARI-1", 100000)], "2025-06-05", False)["ARI-1"][1] == "OVERPAYMENT"
    assert allocate(117013, [facts("ARI-1", 100000)], "2025-06-05", False) == {"ARI-1": (100000, "")}


def test_discount_on_the_invoices_that_have_it_and_full_on_the_rest():
    with_terms = Terms(2.0, 10, "2025-06-01", 100000, "ES")
    no_terms = Terms(None, None, "2025-06-01", 50000, "ES")
    out = allocate(148000, [facts("ARI-1", 100000, with_terms), facts("ARI-2", 50000, no_terms)], "2025-06-05", False)
    assert out == {"ARI-1": (100000, "SHORT_DISCOUNT"), "ARI-2": (50000, "")}


def test_an_advice_without_reason_is_not_withholding_outside_those_countries():
    terms = Terms(None, None, "2025-01-01", 100000, "ES")
    assert decide("ARI-1", "EUR", "EUR", 100000, 90000, deduction=(-10000, None), terms=terms,
                  booking_date="2025-02-01") == (90000, "PARTIAL")
    terms = Terms(None, None, "2025-01-01", 100000, "BR")
    assert decide("ARI-1", "EUR", "EUR", 100000, 90000, deduction=(-10000, None), terms=terms,
                  booking_date="2025-02-01") == (100000, "SHORT_WITHHOLDING")


def _terms(pct=None, total=100000, issued="2025-06-01", country="ES"):
    return Terms(pct, 10 if pct else None, issued, total, country)


def test_a_gap_that_is_the_discount_of_one_invoice_of_several_is_that_invoice_within_terms():
    # BT-2025-0000118: only one of the invoices paid carries a discount, and it is taken.
    items = [("ARI-1", 100000, _terms(2.0, 100000)), ("ARI-2", 50000, _terms(None, 50000))]
    assert allocate(148000, items, "2025-06-05", False) == {"ARI-1": (100000, "SHORT_DISCOUNT"), "ARI-2": (50000, "")}


def test_the_same_gap_out_of_terms_leaves_that_invoice_partial():
    items = [("ARI-1", 100000, _terms(2.0, 100000)), ("ARI-2", 50000, _terms(None, 50000))]
    assert allocate(148000, items, "2025-07-05", False) == {"ARI-1": (98000, "PARTIAL"), "ARI-2": (50000, "")}


def test_a_gap_that_is_the_discount_of_one_of_two_invoices_with_terms_goes_to_that_one():
    items = [("ARI-1", 100000, _terms(2.0, 100000)), ("ARI-2", 50000, _terms(2.0, 50000))]
    assert allocate(149000, items, "2025-06-05", False) == {"ARI-1": (100000, ""), "ARI-2": (50000, "SHORT_DISCOUNT")}


def _whole(total, issued="2025-06-01"):
    return Terms(None, None, issued, total, "ES")


def test_the_partial_of_a_receipt_is_the_only_invoice_it_pays_a_round_share_of():
    # With the others cleared whole, 40 % of the newest is left: the money does not stop at the oldest.
    items = [("ARI-OLD", 123457, _whole(123457, "2025-01-01")), ("ARI-NEW", 200000, _whole(200000))]
    assert allocate(123457 + 80000, items, "2025-06-05", False) == {
        "ARI-OLD": (123457, ""), "ARI-NEW": (80000, "PARTIAL")}
    # BT-2025-0096935's shape: oldest first would leave the old one partial; the round share is the old one's.
    items = [("ARI-OLD", 200000, _whole(200000, "2025-01-01")), ("ARI-NEW", 123457, _whole(123457))]
    assert allocate(123457 + 80000, items, "2025-06-05", False) == {
        "ARI-OLD": (80000, "PARTIAL"), "ARI-NEW": (123457, "")}


def test_two_invoices_with_a_round_share_stay_oldest_first():
    # 40 % of the old one and 40 % of the new one: nothing says which, and the order of always stands.
    items = [("ARI-NEW", 200000, _whole(200000)), ("ARI-OLD", 200000, _whole(200000, "2025-01-01"))]
    assert allocate(280000, items, "2025-06-05", False) == {"ARI-OLD": (200000, ""), "ARI-NEW": (80000, "PARTIAL")}


def test_no_round_share_stays_oldest_first():
    items = [("ARI-NEW", 200000, _whole(200000)), ("ARI-OLD", 123457, _whole(123457, "2025-01-01"))]
    assert allocate(123457 + 77777, items, "2025-06-05", False) == {
        "ARI-OLD": (123457, ""), "ARI-NEW": (77777, "PARTIAL")}


def test_a_round_share_of_a_tiny_invoice_could_be_chance_and_proves_nothing():
    items = [("ARI-OLD", 200000, _whole(200000, "2025-01-01")), ("ARI-NEW", 1000, _whole(1000))]
    assert allocate(200000 + 400, items, "2025-06-05", False) == {"ARI-OLD": (200000, ""), "ARI-NEW": (400, "PARTIAL")}
    items = [("ARI-OLD", 1000, _whole(1000, "2025-01-01")), ("ARI-NEW", 200033, _whole(200033))]
    assert allocate(200033 + 400, items, "2025-06-05", False) == {"ARI-OLD": (1000, ""), "ARI-NEW": (199433, "PARTIAL")}


def test_an_invoice_already_part_paid_takes_no_round_share():
    items = [("ARI-OLD", 123457, _whole(123457, "2025-01-01")), ("ARI-NEW", 150000, _whole(200000))]
    assert allocate(123457 + 60000, items, "2025-06-05", False) == {
        "ARI-OLD": (123457, ""), "ARI-NEW": (60000, "PARTIAL")}
    items = [("ARI-OLD", 150000, _whole(200000, "2025-01-01")), ("ARI-NEW", 123457, _whole(123457))]
    assert allocate(123457 + 60000, items, "2025-06-05", False) == {
        "ARI-OLD": (150000, ""), "ARI-NEW": (33457, "PARTIAL")}


def test_a_document_that_lists_the_items_wins_over_a_round_share():
    items = [("ARI-NEW", 200000, Terms(None, None, "2025-06-01", 200000, "ES", listed_at=0)),
             ("ARI-OLD", 123457, Terms(None, None, "2025-01-01", 123457, "ES", listed_at=1))]
    assert allocate(80000 + 123457, items, "2025-06-05", False) == {
        "ARI-NEW": (200000, ""), "ARI-OLD": (3457, "PARTIAL")}


def test_two_invoices_whose_discount_is_the_gap_are_not_guessed():
    items = [("ARI-1", 50000, _terms(2.0, 50000)), ("ARI-2", 50000, _terms(2.0, 50000))]
    out = allocate(99000, items, "2025-06-05", False)
    assert "SHORT_DISCOUNT" not in {e for _, e in out.values()}


def _says(evidence, exception, item="ARI-1"):
    return Hypothesis(evidence, {item: (100000, exception)}, "")


def test_the_strongest_evidence_wins_whatever_the_order():
    weak, strong = _says(Evidence.DEFAULT, "PARTIAL"), _says(Evidence.PRINTED_REASON, "SHORT_DISPUTE")
    assert choose([weak, strong]) is strong
    assert choose([strong, weak]) is strong


def test_two_different_hypotheses_on_a_level_abstain_and_the_next_one_down_decides():
    tied = [_says(Evidence.ONE_DISCOUNT, "SHORT_DISCOUNT"), _says(Evidence.ONE_DISCOUNT, "SHORT_DISCOUNT", "ARI-2")]
    below = _says(Evidence.DEFAULT, "PARTIAL")
    assert choose([*tied, below]) is below


def test_a_tie_with_nothing_below_chooses_nothing():
    assert choose([_says(Evidence.BOUNDED, "OVERPAYMENT"), _says(Evidence.BOUNDED, "SHORT_BANK_CHARGES")]) is None


def test_the_same_lines_twice_on_a_level_are_not_a_tie():
    # Two rates can round to the gap of a small invoice: they say the same thing.
    assert choose([_says(Evidence.RATE_ON_ALL, "SHORT_WITHHOLDING"), _says(Evidence.RATE_ON_ALL, "SHORT_WITHHOLDING")])


def test_a_node_only_adds_what_it_can_explain():
    no_gap = Gap(0, 100000, [("ARI-1", 100000, PLAIN)], [], "2025-06-05", None)
    assert [h.evidence for node in NODES for h in node(no_gap)] == [Evidence.EXACT]


def test_search_keeps_the_explanation_it_rejected_for_the_evidence():
    out, considered = search(98000, [("ARI-1", 100000, _terms(2.0))], "2025-06-05", False)
    assert out == {"ARI-1": (100000, "SHORT_DISCOUNT")}
    assert [(h.evidence, h.lines) for h in considered] == [
        (Evidence.ALL_DISCOUNTS, {"ARI-1": (100000, "SHORT_DISCOUNT")}),
        (Evidence.DEFAULT, {"ARI-1": (98000, "PARTIAL")})]
    discarded, chosen = as_candidates(considered, "EUR")
    assert (discarded["itemId"], discarded["amountCents"], chosen["itemId"], chosen["amountCents"]) == (
        "ARI-1", 98000, "ARI-1", 100000)
    assert discarded["why"].startswith("discarded DEFAULT PARTIAL")
    assert chosen["why"].startswith("chosen ALL_DISCOUNTS SHORT_DISCOUNT")


def test_one_hypothesis_says_nothing_to_the_evidence():
    assert as_candidates(search(100000, [("ARI-1", 100000, PLAIN)], "2025-06-05", False)[1], "EUR") == []


def test_a_gap_nothing_explains_still_says_what_was_chosen():
    entries = as_candidates(search(60000, [("ARI-1", 100000, PLAIN)], "2025-06-05", False)[1], "EUR")
    assert [(e["amountCents"], e["why"].split(":")[0]) for e in entries] == [(60000, "chosen DEFAULT PARTIAL")]


def test_many_invoices_are_one_entry_per_hypothesis_not_one_per_invoice():
    # A row of the bank line repeats its candidates: an advice of 886 invoices cannot write 886 entries on each row.
    items = [(f"ARI-{n}", 100000, _terms(2.0)) for n in range(3)]
    discarded, chosen = as_candidates(search(294000, items, "2025-06-05", False)[1], "EUR")
    assert chosen["amountCents"] == 300000 and chosen["why"].startswith("chosen ALL_DISCOUNTS SHORT_DISCOUNT x3:")
    assert discarded["amountCents"] == 294000 and discarded["why"].startswith("discarded DEFAULT -")


def test_the_hypotheses_of_a_foreign_payment_say_what_its_row_says():
    out, considered = search(98000, [("ARI-1", 100000, _terms(2.0))], "2025-06-05", True)
    assert out == {"ARI-1": (100000, "FX_DIFFERENCE")}
    assert as_candidates(considered, "USD")[-1]["why"].startswith("chosen ALL_DISCOUNTS FX_DIFFERENCE")


def test_a_printed_deduction_weighs_what_decide_chose_against_what_nothing_explains():
    considered = weighed("ARI-1", False, 100000, 95000, (-5000, "GOODS DAMAGED"), PLAIN, "2025-06-05")
    assert [(h.evidence, h.lines["ARI-1"]) for h in considered] == [
        (Evidence.PRINTED_REASON, (95000, "SHORT_DISPUTE")), (Evidence.DEFAULT, (95000, "PARTIAL"))]
    assert decide("ARI-1", "EUR", "EUR", 100000, 95000, deduction=(-5000, "GOODS DAMAGED"), terms=PLAIN,
                  booking_date="2025-06-05") == considered[0].lines["ARI-1"]


def test_a_deduction_that_leaves_nothing_to_explain_weighs_nothing():
    assert weighed("ARI-1", False, 100000, 100000, (-5000, None), PLAIN, "2025-06-05") == []
    assert weighed("ARI-1", False, 100000, 95000, (0, None), PLAIN, "2025-06-05") == []
    assert weighed("ARI-1", False, 0, 95000, (-5000, None), PLAIN, "2025-06-05") == []


def test_cash_beyond_what_is_cited_leaves_each_invoice_as_its_terms_say():
    items = [("ARI-1", 100000, _terms(2.0, 100000)), ("ARI-2", 50000, _terms(2.0, 50000, "2025-05-01")),
             ("ARI-3", 40000, _terms(None, 40000)), ("ARI-4", 30000, _terms(2.0, 90000))]
    assert allocate(900000, items, "2025-06-05", False) == {
        "ARI-1": (100000, "SHORT_DISCOUNT"), "ARI-2": (50000, ""), "ARI-3": (40000, ""), "ARI-4": (30000, "")}


def test_one_invoice_in_terms_inside_a_larger_payment_took_its_discount():
    assert allocate(200000, [("ARI-1", 100000, _terms(2.0, 100000))], "2025-06-05", False) == {
        "ARI-1": (100000, "SHORT_DISCOUNT")}


def test_cash_a_little_over_the_invoices_is_no_sign_of_more_invoices():
    items = [("ARI-1", 100000, _terms(2.0, 100000)), ("ARI-2", 50000, _terms(2.0, 50000))]
    assert allocate(150100, items, "2025-06-05", False) == {"ARI-1": (100000, ""), "ARI-2": (50000, "")}


def _plain(total, country="ES"):
    return Terms(None, None, "2025-06-01", total, country)


def test_a_round_amount_paid_over_a_single_invoice_is_an_overpayment():
    # POLICIES §3: more than the open amount of one invoice. A round excess is what someone rounding up sends.
    for excess in (10000, 500, 50000):
        assert allocate(120000 + excess, [("ARI-1", 120000, _plain(120000))], "2025-06-05", False)["ARI-1"] == (
            120000, "OVERPAYMENT")


def test_an_excess_that_is_not_round_means_the_text_cited_part_of_what_the_cash_pays():
    assert allocate(120000 + 3713 * 10, [("ARI-1", 120000, _plain(120000))], "2025-06-05", False)["ARI-1"][1] == ""


def test_a_round_excess_not_smaller_than_the_invoice_is_not_an_overpayment_of_it():
    assert allocate(120000 + 120000, [("ARI-1", 120000, _plain(120000))], "2025-06-05", False)["ARI-1"][1] == ""


def test_a_fee_the_bank_states_is_bank_charges_whatever_the_country():
    items = [("ARI-1", 100000, _plain(100000))]
    assert allocate(98000, items, "2025-06-05", False, 1.0, fee_stated=True)["ARI-1"] == (100000, "SHORT_BANK_CHARGES")


def test_with_no_fee_stated_a_customer_in_sepa_is_still_partial():
    items = [("ARI-1", 100000, _plain(100000))]
    assert allocate(98000, items, "2025-06-05", False, 1.0)["ARI-1"] == (98000, "PARTIAL")


def test_a_stated_fee_past_the_limits_of_the_policy_is_not_bank_charges():
    items = [("ARI-1", 100000, _plain(100000))]
    assert allocate(90000, items, "2025-06-05", False, 1.0, fee_stated=True)["ARI-1"] == (90000, "PARTIAL")


def test_fee_is_stated_only_with_the_amount_and_currency_of_the_shortfall():
    assert fee_stated("X /CHGS/EUR20,00", "EUR", 2000)
    assert not fee_stated("X /CHGS/EUR20,00", "EUR", 2100)
    assert not fee_stated("X /CHGS/USD20,00", "EUR", 2000)
    assert not fee_stated("X", "EUR", 2000)


def test_discount_and_withholding_are_read_in_portuguese_and_french():
    terms = Terms(2.0, 10, "2025-06-01", 100000, "ES")
    assert line(100000, 98000, (-2000, "DESCONTO"), terms=terms)[1] == "SHORT_DISCOUNT"
    for word in ("RETENÇÃO", "RETENCAO", "RETENUE"):
        assert line(100000, 90000, (-10000, word))[1] == "SHORT_WITHHOLDING"


def discounted(item, cents, issued):
    return (item, cents, Terms(2.0, 10, issued, cents, "ES"))


def test_the_gap_is_the_discount_of_some_invoices_one_in_terms_and_one_late():
    """BT-2025-0139661: 13.803,34 for 9.900,09 (late, 198,00 left), 2.424,73 whole and 1.710,73 in terms (34,21)."""
    invoices = [discounted("ARI-LATE", 990009, "2024-12-01"), discounted("ARI-WHOLE", 242473, "2025-04-08"),
                discounted("ARI-IN", 171073, "2025-05-01")]
    assert allocate(1380334, invoices, "2025-05-12", False) == {
        "ARI-LATE": (970209, "PARTIAL"), "ARI-WHOLE": (242473, ""), "ARI-IN": (171073, "SHORT_DISCOUNT")}


def test_two_sets_of_discounts_that_explain_the_gap_tie_and_neither_is_taken():
    invoices = [discounted("ARI-1", 100000, "2025-05-01"), discounted("ARI-2", 100000, "2025-05-02"),
                discounted("ARI-3", 150000, "2025-05-03"), discounted("ARI-4", 50000, "2025-05-04")]
    out = allocate(396000, invoices, "2025-05-06", False)
    assert "SHORT_DISCOUNT" not in {exception for _, exception in out.values()}


def test_a_set_of_discounts_chance_would_explain_proves_nothing():
    invoices = [discounted(f"ARI-{n:02}", 200 * 2 ** n, "2025-05-01") for n in range(12)]
    cash = sum(cents for _, cents, _ in invoices) - 12  # exactly the discounts of the two smallest, 4 and 8
    out = allocate(cash, invoices, "2025-05-06", False)
    assert "SHORT_DISCOUNT" not in {exception for _, exception in out.values()}

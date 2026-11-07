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
    search,
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
    assert allocate(117000, [facts("ARI-1", 100000)], "2025-06-05", False) == {"ARI-1": (100000, "")}


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
    entry = as_candidates(considered, "EUR")[0]
    assert (entry["itemId"], entry["amountCents"]) == ("ARI-1", 100000)
    assert entry["why"].startswith("chosen ALL_DISCOUNTS SHORT_DISCOUNT") and "DEFAULT PARTIAL 98000" in entry["why"]


def test_one_hypothesis_says_nothing_to_the_evidence():
    assert as_candidates(search(100000, [("ARI-1", 100000, PLAIN)], "2025-06-05", False)[1], "EUR") == []

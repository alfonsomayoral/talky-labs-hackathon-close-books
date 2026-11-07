"""POLICIES §2-§3, clause by clause. Amounts from real lines of sample/TRAIN where the comment says so."""
from __future__ import annotations

from closebooks.policy import Terms, allocate, cross_border, decide

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
    assert line(100000, 98750, (-1250, None))[1] == "SHORT_WITHHOLDING"
    assert line(100000, 98500, (-1500, None))[1] == "SHORT_WITHHOLDING"
    assert line(100000, 90000, (-10000, None))[1] == "SHORT_WITHHOLDING"
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
    assert allocate(80407, [facts("ARI-1", 75407)], "2025-06-05", False) == {"ARI-1": (75407, "OVERPAYMENT")}


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


def test_a_huge_excess_is_not_an_overpayment_of_that_invoice_but_an_incomplete_citation():
    # Real overpayments stay under 32 % of the invoice (p99 in the holdout); false ones have a median excess of x5.
    assert allocate(500000, [facts("ARI-1", 100000)], "2025-06-05", False) == {"ARI-1": (100000, "")}


def test_cross_border_signal_comes_from_the_iso_code_or_the_bank_text():
    assert cross_border("PMNT/RCDT/XBCT", "WIRE IN /ORG/LAKEVIEW")
    assert cross_border("13", "TRANSFER. EN DIV. | CDDJCBXX | GASTOS SHA")
    assert not cross_border("PMNT/RCDT/ESCT", "ACH CREDIT WATER CARE BLUE")


def test_duplicate_needs_the_exact_amount_of_the_settled_item():
    settled = Terms(None, None, "2025-01-01", 100000, "ES")
    out = allocate(100000, [facts("ARI-1", 0, settled)], "2025-06-05", False)
    assert out == {"ARI-1": (100000, "DUPLICATE_PAYMENT")}
    assert allocate(40000, [facts("ARI-1", 0, settled)], "2025-06-05", False) == {"ARI-1": (40000, "")}
    assert line(0, 40000, None, terms=settled) == (40000, "")
    assert line(0, 100000, None, terms=settled) == (100000, "DUPLICATE_PAYMENT")

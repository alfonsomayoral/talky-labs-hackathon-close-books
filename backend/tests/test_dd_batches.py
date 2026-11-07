from __future__ import annotations

import polars as pl
from test_payment_runs import golden_pairs, proposed_pairs

from closebooks.rules import dd_batches

M1, M2 = "VTM-ES-0000001", "VTM-ES-0000002"
HEADER = ("batch_id,scheme,collection_date,account_id,currency,batch_total,end_to_end_id,mandate_id,debtor_name,"
          "debtor_iban,amount,remittance_info,re_presentation\n")


def batch(batch_id, date, receipts, account="ES01-PENA-EUR", total=None):
    """receipts: (mandate, amount, remittance_info, re_presentation)"""
    total = total if total is not None else sum(r[1] for r in receipts)
    return "".join(f"{batch_id},SEPA,{date},{account},EUR,{total:.2f},{batch_id}-{n:04d},{m},X,,{a:.2f},{ref},{rp}\n"
                   for n, (m, a, ref, rp) in enumerate(receipts, 1))


def item(n, number, cents, entity="ES01", party="C1"):
    return {"item_id": f"ARI-2025-000000{n}", "entity": entity, "party_id": party, "document_number": number,
            "total_cents": cents}


def credit(txn_id, text, cents, account="ES01-PENA-EUR", date="2025-05-28"):
    return {"bank_txn_id": txn_id, "account_id": account, "booking_date": date, "amount_cents": cents, "text": text}


def test_batch_credit_settles_the_receipts_of_its_file_and_nothing_else(sample):
    # The golden of a batch credit is every receipt of that batch: June of the sample has a dozen of them.
    proposals = {t: p for t, p in dd_batches.propose(sample).items() if p.rule == "FILE-DD-BATCH"}
    mine, gold = proposed_pairs(proposals), golden_pairs(["ar_dd_batch"])
    assert len(mine) > 1000
    assert mine <= gold
    assert len(mine) / len(gold) > 0.99


def test_batch_id_repeated_in_two_accounts_is_the_batch_of_the_account_that_was_credited(phase_factory):
    files = {"direct_debit_batches": HEADER +
             batch("01250528001", "2025-05-28", [(M1, 100.0, "F-1", "N")]) +
             batch("01250528001", "2025-05-28", [(M2, 100.0, "F-2", "N")], account="ES02-PENA-EUR")}
    phase = phase_factory(
        items=[item(1, "F-1", 10000), item(2, "F-2", 10000, entity="ES02")],
        txns=[credit("BT-1", "SEPA EINZUG 01250528001 1 POSTEN", 10000, account="ES02-PENA-EUR")],
        files=files, accounts=(("ES01-PENA-EUR", "ES01"), ("ES02-PENA-EUR", "ES02")))
    assert dd_batches.propose(phase)["BT-1"].lines == [("ARI-2025-0000002", 10000)]


def test_credit_that_is_not_the_total_of_the_batch_is_not_claimed(phase_factory):
    files = {"direct_debit_batches": HEADER + batch("01250528001", "2025-05-28", [(M1, 100.0, "F-1", "N")])}
    phase = phase_factory(items=[item(1, "F-1", 10000)], files=files,
                          txns=[credit("BT-1", "SEPA EINZUG 01250528001 1 POSTEN", 9999)])
    assert dd_batches.propose(phase) == {}


def test_receipt_without_prefix_is_found_by_its_trailing_digits_and_amount(phase_factory):
    # "RECIBO 0108480" for invoice INV21-0108480; another entity-wide invoice ends alike but has another amount.
    files = {"direct_debit_batches": HEADER + batch("01250528001", "2025-05-28", [(M1, 100.0, "RECIBO 0108480", "N")])}
    phase = phase_factory(
        items=[item(1, "INV21-0108480", 10000), item(2, "FV25-0108480", 5000)], files=files,
        txns=[credit("BT-1", "SEPA EINZUG 01250528001 1 POSTEN", 10000)])
    assert dd_batches.propose(phase)["BT-1"].lines == [("ARI-2025-0000001", 10000)]


def test_cut_number_that_ends_like_an_invoice_of_another_amount_is_not_that_invoice(phase_factory):
    files = {"direct_debit_batches": HEADER + batch("01250528001", "2025-05-28", [(M1, 100.0, "RECIBO 0108480", "N")])}
    phase = phase_factory(items=[item(1, "INV21-0108480", 9000)], files=files,
                          txns=[credit("BT-1", "SEPA EINZUG 01250528001 1 POSTEN", 10000)])
    assert dd_batches.propose(phase) == {}


def test_receipt_that_points_to_two_invoices_is_left_out_not_guessed(phase_factory):
    files = {"direct_debit_batches": HEADER + batch("01250528001", "2025-05-28",
                                           [(M1, 100.0, "RECIBO 0108480", "N"), (M2, 50.0, "F-2", "N")])}
    phase = phase_factory(
        items=[item(1, "INV21-0108480", 10000), item(2, "FV25-0108480", 10000), item(3, "F-2", 5000)], files=files,
        txns=[credit("BT-1", "SEPA EINZUG 01250528001 2 POSTEN", 15000)])
    assert dd_batches.propose(phase)["BT-1"].lines == [("ARI-2025-0000003", 5000)]


def test_receipt_with_a_typo_in_the_number_is_found_by_mandate_and_amount(phase_factory):
    files = {"direct_debit_batches": HEADER + batch("01250528001", "2025-05-28", [(M1, 100.0, "F-9", "N")])}
    phase = phase_factory(
        items=[item(1, "F-1", 10000, party="C1"), item(2, "F-2", 10000, party="C2")], files=files,
        customers=(("C1", M1), ("C2", M2)),
        txns=[credit("BT-1", "SEPA EINZUG 01250528001 1 POSTEN", 10000)])
    assert dd_batches.propose(phase)["BT-1"].lines == [("ARI-2025-0000001", 10000)]


def returns_phase(phase_factory, reason, first_delay_days, also=()):
    """Two receipts of one mandate and amount, 28 days apart; the return comes `first_delay_days` after the later."""
    files = {"direct_debit_batches": HEADER +
             batch("01250401001", "2025-04-01", [(M1, 100.0, "F-1", "N")]) +
             batch("01250429002", "2025-04-29", [(M1, 100.0, "F-2", "N")])}
    from datetime import date, timedelta
    booked = (date(2025, 4, 29) + timedelta(days=first_delay_days)).isoformat()
    return phase_factory(
        items=[item(1, "F-1", 10000), item(2, "F-2", 10000)], files=files,
        txns=[credit("BT-R", f"RUECKLASTSCHRIFT {reason} MREF+{M1}", -10000, date=booked), *also])


def test_return_without_batch_reverses_the_latest_receipt_that_had_time_to_come_back(phase_factory):
    proposal = dd_batches.propose(returns_phase(phase_factory, "AM04", 6))["BT-R"]
    assert (proposal.rule, proposal.returned, proposal.lines) == ("FILE-DD-RETURN", True, [("ARI-2025-0000002", 10000)])


def test_refund_claim_comes_weeks_later_so_it_reverses_the_earlier_receipt(phase_factory):
    # MD06 six days after the second receipt cannot be that one: SEPA allows the debtor to claim for eight weeks.
    proposal = dd_batches.propose(returns_phase(phase_factory, "MD06", 6))["BT-R"]
    assert proposal.lines == [("ARI-2025-0000001", 10000)]


def test_two_returns_of_the_same_mandate_and_amount_reverse_two_receipts(phase_factory):
    # Both come back soon after the second receipt: the first takes it, the next cannot take it again.
    first = credit("BT-S", f"RUECKLASTSCHRIFT AM04 MREF+{M1}", -10000, date="2025-05-01")
    proposals = dd_batches.propose(returns_phase(phase_factory, "AM04", 6, also=[first]))
    assert [proposals[t].lines[0][0] for t in ("BT-S", "BT-R")] == ["ARI-2025-0000002", "ARI-2025-0000001"]


def test_of_two_receipts_that_could_come_back_the_one_presented_again_afterwards_did(phase_factory):
    # Same mandate and amount two days apart, both inside the days a return takes; F-1 is collected again on 20 May.
    files = {"direct_debit_batches": HEADER
             + batch("01250427001", "2025-04-27", [(M1, 100.0, "F-1", "N")])
             + batch("01250429002", "2025-04-29", [(M1, 100.0, "F-2", "N")])
             + batch("01250520003", "2025-05-20", [(M1, 100.0, "F-1", "Y")])}
    phase = phase_factory(items=[item(1, "F-1", 10000), item(2, "F-2", 10000)], files=files,
                          txns=[credit("BT-R", f"RUECKLASTSCHRIFT AM04 MREF+{M1}", -10000, date="2025-05-05")])
    assert dd_batches.propose(phase)["BT-R"].lines == [("ARI-2025-0000001", 10000)]


def test_return_whose_batch_is_before_the_phase_reverses_the_receipt_presented_again_afterwards(phase_factory):
    files = {"direct_debit_batches": HEADER + batch("01250520003", "2025-05-20", [(M1, 100.0, "F-1", "Y")])}
    phase = phase_factory(items=[item(1, "F-1", 10000)], files=files,
                          txns=[credit("BT-R", f"RUECKLASTSCHRIFT AM04 MREF+{M1}", -10000, date="2025-05-10")])
    assert dd_batches.propose(phase)["BT-R"].lines == [("ARI-2025-0000001", 10000)]


def _return_then_transfers(phase_factory, *transfers):
    """F-2 is what the delay of the return says; F-1 is what a later transfer may say."""
    files = {"direct_debit_batches": HEADER
             + batch("01250401001", "2025-04-01", [(M1, 100.0, "FA25000111", "N")])
             + batch("01250429002", "2025-04-29", [(M1, 100.0, "FA25000222", "N")])}
    return phase_factory(items=[item(1, "FA25000111", 10000), item(2, "FA25000222", 10000)], files=files,
                         txns=[credit("BT-R", f"RUECKLASTSCHRIFT AM04 MREF+{M1}", -10000, date="2025-05-05"),
                               *transfers])


def test_of_two_receipts_the_one_whose_invoice_a_later_transfer_cites_is_the_one_that_came_back(phase_factory):
    paid = credit("BT-P", "TRANSFER PAGO FA25000111", 10000, date="2025-05-20")
    proposal = dd_batches.propose(_return_then_transfers(phase_factory, paid))["BT-R"]
    assert proposal.lines == [("ARI-2025-0000001", 10000)]


def test_a_transfer_may_cite_only_the_end_of_the_number(phase_factory):
    paid = credit("BT-P", "PAGO RECIBO 5000111", 10000, date="2025-05-20")
    proposal = dd_batches.propose(_return_then_transfers(phase_factory, paid))["BT-R"]
    assert proposal.lines == [("ARI-2025-0000001", 10000)]


def test_later_transfers_that_say_nothing_about_which_receipt_leave_the_delay_to_decide(phase_factory):
    usual = [("ARI-2025-0000002", 10000)]
    both = [credit("BT-P", "PAGO FA25000111", 10000, date="2025-05-20"),
            credit("BT-Q", "PAGO FA25000222", 10000, date="2025-05-21")]
    assert dd_batches.propose(_return_then_transfers(phase_factory, *both))["BT-R"].lines == usual
    other_amount = credit("BT-P", "PAGO FA25000111", 9000, date="2025-05-20")
    assert dd_batches.propose(_return_then_transfers(phase_factory, other_amount))["BT-R"].lines == usual
    before = credit("BT-P", "PAGO FA25000111", 10000, date="2025-05-01")
    assert dd_batches.propose(_return_then_transfers(phase_factory, before))["BT-R"].lines == usual
    too_late = credit("BT-P", "PAGO FA25000111", 10000, date="2025-07-20")
    assert dd_batches.propose(_return_then_transfers(phase_factory, too_late))["BT-R"].lines == usual


def test_return_of_a_mandate_with_no_receipt_of_that_amount_is_not_forced(phase_factory):
    phase = returns_phase(phase_factory, "AM04", 6)
    phase.txns = phase.txns.with_columns((pl.col("amount_cents") - 1).alias("amount_cents"))
    assert dd_batches.propose(phase) == {}


def test_returns_pair_with_the_receipts_they_reverse(sample):
    proposals = {t: p for t, p in dd_batches.propose(sample).items() if p.rule == "FILE-DD-RETURN"}
    mine, gold = proposed_pairs(proposals), golden_pairs(["ar_dd_returned"])
    assert len(mine) > 100
    assert len(mine & gold) / len(mine) > 0.95

from __future__ import annotations

from test_payment_runs import golden_pairs, proposed_pairs

from closebooks.rules import cheque_deposits

HEADER = ("deposit_id,deposit_date,account_id,currency,deposit_total,cheque_number,drawer,drawer_bank_routing,amount,"
          "stub_reference\n")


def deposit(deposit_id, date, cheques, account="ES01-PENA-EUR"):
    """cheques: (cheque_number, drawer, amount, stub_reference)"""
    total = sum(c[2] for c in cheques)
    return "".join(f"{deposit_id},{date},{account},EUR,{total:.2f},{n},{d},123,{a:.2f},{s or ''}\n"
                   for n, d, a, s in cheques)


def invoice(n, number, cents, name="Acme SL"):
    return {"item_id": f"ARI-2025-000000{n}", "entity": "ES01", "document_number": number, "total_cents": cents,
            "party_name": name}


def txn(txn_id, text, cents, date="2025-05-28", account="ES01-PENA-EUR"):
    return {"bank_txn_id": txn_id, "account_id": account, "booking_date": date, "amount_cents": cents, "text": text}


def test_deposit_clears_the_cheques_of_its_file(sample):
    proposals = {t: p for t, p in cheque_deposits.propose(sample).items() if p.rule == "FILE-CHEQUE"}
    mine, gold = proposed_pairs(proposals), golden_pairs(["ar_cheque_deposit"])
    assert len(mine) > 100
    assert mine <= gold
    assert len(mine) / len(gold) > 0.99


def test_each_cheque_finds_its_invoice_by_stub_by_cut_stub_or_by_drawer_and_amount(phase_factory):
    files = {"cheque_deposits": HEADER + deposit("RCH25052802580", "2025-05-28", [
        ("1000001", "Acme SL", 100.0, "FA250200023"), ("1000002", "Beta SA", 50.0, "200024"),
        ("1000003", "Gamma SL", 25.0, None)])}
    phase = phase_factory(
        items=[invoice(1, "FA250200023", 10000), invoice(2, "FA250200024", 5000, "Beta SA"),
               invoice(3, "FA250200099", 2500, "Gamma SL"), invoice(4, "FA250200098", 2500, "Other SL")],
        files=files, txns=[txn("BT-1", "REMISE DE CHEQUES RCH25052802580 3 CHQ", 17500)])
    proposal = cheque_deposits.propose(phase)["BT-1"]
    assert proposal.rule == "FILE-CHEQUE"
    assert dict(proposal.lines) == {"ARI-2025-0000001": 10000, "ARI-2025-0000002": 5000, "ARI-2025-0000003": 2500}


def test_cheque_whose_drawer_and_amount_fit_two_invoices_is_left_out_and_the_rest_is_kept(phase_factory):
    files = {"cheque_deposits": HEADER + deposit("RCH25052802580", "2025-05-28", [
        ("1000001", "Acme SL", 100.0, "FA250200023"), ("1000003", "Gamma SL", 25.0, None)])}
    phase = phase_factory(
        items=[invoice(1, "FA250200023", 10000), invoice(3, "FA250200099", 2500, "Gamma SL"),
               invoice(4, "FA250200098", 2500, "Gamma SL")],
        files=files, txns=[txn("BT-1", "REMISE DE CHEQUES RCH25052802580 2 CHQ", 12500)])
    assert cheque_deposits.propose(phase)["BT-1"].lines == [("ARI-2025-0000001", 10000)]


def test_deposit_id_repeated_in_two_accounts_is_the_deposit_of_the_account_credited(phase_factory):
    files = {"cheque_deposits": HEADER + deposit("RCH25052802580", "2025-05-28", [("1000001", "A", 100.0, "F-1")])
             + deposit("RCH25052802580", "2025-05-28", [("1000002", "B", 100.0, "F-2")], account="ES02-PENA-EUR")}
    phase = phase_factory(items=[invoice(1, "F-1", 10000), {**invoice(2, "F-2", 10000), "entity": "ES02"}],
                          accounts=(("ES01-PENA-EUR", "ES01"), ("ES02-PENA-EUR", "ES02")), files=files,
                          txns=[txn("BT-1", "REMISE DE CHEQUES RCH25052802580 1 CHQ", 10000, account="ES02-PENA-EUR")])
    assert cheque_deposits.propose(phase)["BT-1"].lines == [("ARI-2025-0000002", 10000)]


def test_credit_that_is_not_the_total_of_the_deposit_is_not_claimed(phase_factory):
    files = {"cheque_deposits": HEADER + deposit("RCH25052802580", "2025-05-28", [("1000001", "A", 100.0, "F-1")])}
    phase = phase_factory(items=[invoice(1, "F-1", 10000)], files=files,
                          txns=[txn("BT-1", "REMISE DE CHEQUES RCH25052802580 1 CHQ", 9000)])
    assert cheque_deposits.propose(phase) == {}


def test_returned_cheque_reopens_the_invoice_of_that_cheque_number(phase_factory):
    files = {"cheque_deposits": HEADER + deposit("RCH25052802580", "2025-05-28", [
        ("5799000", "A", 100.0, "F-1"), ("5799001", "B", 100.0, "F-2")])}
    phase = phase_factory(items=[invoice(1, "F-1", 10000), invoice(2, "F-2", 10000)], files=files,
                          txns=[txn("BT-R", "CHEQUE IMPAYE 5799001 NSF", -10000, date="2025-06-03")])
    proposal = cheque_deposits.propose(phase)["BT-R"]
    assert (proposal.rule, proposal.returned, proposal.lines) == ("FILE-CHEQUE-RETURN", True,
                                                                  [("ARI-2025-0000002", 10000)])


def test_returned_cheque_of_another_amount_is_not_forced(phase_factory):
    files = {"cheque_deposits": HEADER + deposit("RCH25052802580", "2025-05-28", [("5799000", "A", 100.0, "F-1")])}
    phase = phase_factory(items=[invoice(1, "F-1", 10000)], files=files,
                          txns=[txn("BT-R", "CHEQUE IMPAYE 5799000 NSF", -9000, date="2025-06-03")])
    assert cheque_deposits.propose(phase) == {}

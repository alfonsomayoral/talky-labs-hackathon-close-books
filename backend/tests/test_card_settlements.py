from __future__ import annotations

from test_payment_runs import golden_pairs, proposed_pairs

from closebooks.rules import card_settlements

HEADER = ("settlement_id,acquirer,merchant_id,settlement_date,account_id,currency,order_number,card,auth_code,"
          "operation_date,gross,fee,net\n")
MID, MID2, DAY = "097759027", "021899465", "2025-05-28"


def settlement(merchant, operations, account="ES01-PENA-EUR"):
    """operations: (order_number, card, gross, fee). Settlement id: last digits of the merchant and the date."""
    sid = merchant[-4:] + DAY.replace("-", "")[2:]
    return "".join(f"{sid},PayNexo,{merchant},{DAY},{account},EUR,{o},{c},111111,{DAY},{g:.2f},{f:.2f},{g - f:.2f}\n"
                   for o, c, g, f in operations)


def order(n, number, cents):
    return {"item_id": f"ARI-2025-000000{n}", "entity": "ES01", "document_number": number, "total_cents": cents}


def credit(txn_id, text, cents, date=DAY, account="ES01-PENA-EUR"):
    return {"bank_txn_id": txn_id, "account_id": account, "booking_date": date, "amount_cents": cents, "text": text}


def test_settlement_clears_its_orders_at_gross_whatever_the_fee(sample):
    proposals = {t: p for t, p in card_settlements.propose(sample).items() if p.rule == "FILE-CARD"}
    mine, gold = proposed_pairs(proposals), golden_pairs(["ar_card_settlement"])
    assert len(mine) > 1000
    assert mine <= gold
    assert len(mine) / len(gold) > 0.99


def test_credit_has_the_net_but_the_lines_are_the_gross_of_each_order(phase_factory):
    ops = [("WEB25-0000001", "****1111", 100.0, 1.0), ("WEB25-0000002", "****2222", 50.0, 0.5)]
    phase = phase_factory(items=[order(1, "WEB25-0000001", 10000), order(2, "WEB25-0000002", 5000)],
                          files={"card_settlements": HEADER + settlement(MID, ops)},
                          txns=[credit("BT-1", f"CARD SETTLEMENT MID {MID} 2025-05-27 2 TRX", 14850)])
    assert card_settlements.propose(phase)["BT-1"].lines == [("ARI-2025-0000001", 10000), ("ARI-2025-0000002", 5000)]


def test_two_merchants_with_the_same_net_the_same_day_are_told_apart_by_the_merchant_in_the_text(phase_factory):
    file = (settlement(MID, [("WEB25-0000001", "****1111", 100.0, 1.0)])
            + settlement(MID2, [("WEB25-0000002", "****2222", 100.0, 1.0)]))
    phase = phase_factory(items=[order(1, "WEB25-0000001", 10000), order(2, "WEB25-0000002", 10000)],
                          files={"card_settlements": HEADER + file},
                          txns=[credit("BT-1", f"LIQUIDACION REMESA | COMERC {MID2} REM 9465250528", 9900)])
    assert card_settlements.propose(phase)["BT-1"].lines == [("ARI-2025-0000002", 10000)]


def test_credit_of_the_same_net_that_names_no_merchant_of_the_account_is_not_a_settlement(phase_factory):
    file = settlement(MID, [("WEB25-0000001", "****1111", 100.0, 1.0)])
    phase = phase_factory(items=[order(1, "WEB25-0000001", 10000)], files={"card_settlements": HEADER + file},
                          txns=[credit("BT-1", "TRANSFERENCIA DE CLIENTE", 9900)])
    assert card_settlements.propose(phase) == {}


def test_settlement_id_repeated_in_another_account_is_a_different_settlement(phase_factory):
    file = (settlement(MID, [("WEB25-0000001", "****1111", 100.0, 1.0)])
            + settlement(MID, [("WEB25-0000002", "****2222", 100.0, 1.0)], account="ES02-PENA-EUR"))
    phase = phase_factory(items=[order(1, "WEB25-0000001", 10000)], files={"card_settlements": HEADER + file},
                          accounts=(("ES01-PENA-EUR", "ES01"), ("ES02-PENA-EUR", "ES02")),
                          txns=[credit("BT-1", f"CARD SETTLEMENT MID {MID} 2025-05-27", 9900)])
    assert card_settlements.propose(phase)["BT-1"].lines == [("ARI-2025-0000001", 10000)]


def test_order_that_matches_no_invoice_is_left_out_and_the_rest_is_kept(phase_factory):
    ops = [("WEB25-0000001", "****1111", 100.0, 1.0), ("WEB25-9999999", "****2222", 50.0, 0.5)]
    phase = phase_factory(items=[order(1, "WEB25-0000001", 10000)],
                          files={"card_settlements": HEADER + settlement(MID, ops)},
                          txns=[credit("BT-1", f"CARD SETTLEMENT MID {MID} 2025-05-27 2 TRX", 14850)])
    assert card_settlements.propose(phase)["BT-1"].lines == [("ARI-2025-0000001", 10000)]


def test_chargeback_reopens_the_order_of_that_card_merchant_and_amount(phase_factory):
    ops = [("WEB25-0000001", "****1111", 100.0, 1.0), ("WEB25-0000002", "****1111", 70.0, 0.7)]
    phase = phase_factory(items=[order(1, "WEB25-0000001", 10000), order(2, "WEB25-0000002", 7000)],
                          files={"card_settlements": HEADER + settlement(MID, ops)},
                          txns=[credit("BT-C", f"CHARGEBACK ****1111 MID {MID}", -7000, date="2025-06-10")])
    proposal = card_settlements.propose(phase)["BT-C"]
    assert (proposal.rule, proposal.returned, proposal.lines) == ("FILE-CARD-CHARGEBACK", True,
                                                                  [("ARI-2025-0000002", 7000)])


def test_chargeback_of_an_amount_no_operation_of_that_card_had_is_not_forced(phase_factory):
    file = settlement(MID, [("WEB25-0000001", "****1111", 100.0, 1.0)])
    phase = phase_factory(items=[order(1, "WEB25-0000001", 10000)], files={"card_settlements": HEADER + file},
                          txns=[credit("BT-C", f"CHARGEBACK ****1111 MID {MID}", -9000, date="2025-06-10")])
    assert card_settlements.propose(phase) == {}

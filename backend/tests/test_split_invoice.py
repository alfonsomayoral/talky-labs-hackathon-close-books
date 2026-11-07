"""Two receipts that cite one invoice and add up to all they cite. Invented cases, none from the golden."""
from __future__ import annotations

from types import SimpleNamespace

import polars as pl
from test_party_amount import item, masters

from closebooks import rules
from closebooks.model import Proposal
from closebooks.resolve import resolve
from closebooks.rules import split_invoice

ONLY_FIRST, COMMON, ONLY_SECOND = "ARI-1", "ARI-2", "ARI-3"
CUSTOMERS = (("C1", "E1", "Piscinas Alameda S.L.", None, None, None, None, None),
             ("C2", "E1", "Riegos Vallejo S.L.", None, None, None, None, None))


def invoices():
    # The common invoice is the oldest: oldest first would not leave the open balance where the citations do.
    return [item(ONLY_FIRST, "C1", "FA2400011", 30000), item(COMMON, "C1", "FA2400022", 50000, issued="2023-12-01"),
            item(ONLY_SECOND, "C1", "FA2400033", 20000)]


def receipt(txn_id, cents, numbers, date, name="Piscinas Alameda S.L.", currency="EUR"):
    return {"bank_txn_id": txn_id, "booking_date": date, "amount_cents": cents, "currency": currency, "bank": "X",
            "bank_code": "", "bank_subcode": "", "text": "TRANSFERENCIA FRAS " + " ".join(numbers), "orig_cents": None,
            "orig_currency": None, "amount_eur_cents": None, "entity": "E1", "counterparty_name": name,
            "counterparty_account": None, "remittance_info": None, "ref1": None, "ref2": None, "end_to_end_id": None}


def phase_of(items, txns, customers=CUSTOMERS):
    table = pl.DataFrame(items, schema_overrides={"customer_po": pl.String}).with_columns(
        pl.lit(None, pl.String).alias("payment_terms"))
    of_phase = masters(customers)
    masters_of = {**of_phase, "customers": of_phase["customers"].with_columns(pl.lit("ES").alias("country")),
                  "payment_terms": pl.DataFrame(schema={"code": pl.String, "early_payment_discount_pct": pl.String,
                                                        "discount_days": pl.String})}
    return SimpleNamespace(items=table, masters=masters_of, start="2021-01-01", txns=pl.DataFrame(
        txns, schema_overrides={k: pl.String for k in ("orig_currency", "remittance_info", "ref1", "ref2",
                                                       "end_to_end_id", "counterparty_account", "counterparty_name")}
        | {"orig_cents": pl.Int64, "amount_eur_cents": pl.Int64}))


COMMON_NUMBER = "FA2400022"
FIRST = ("FA2400011", COMMON_NUMBER)
SECOND = (COMMON_NUMBER, "FA2400033")


def pair(first_cents=45000, second_cents=55000, first_date="2024-06-01", second_date="2024-06-20"):
    return [receipt("BT-1", first_cents, FIRST, first_date), receipt("BT-2", second_cents, SECOND, second_date)]


def proposed(items, txns, claimed=None):
    return split_invoice.propose(phase_of(items, txns), claimed or {})


def walked(phase, proposals):
    rows, balances = resolve(phase, proposals, rules.stateful(phase, proposals))
    return [(r.bank_txn_id, r.item_id, r.amount_cents, r.exception) for r in rows], balances


def test_first_closes_its_own_and_applies_the_rest_to_the_common_the_second_closes_the_rest():
    found = proposed(invoices(), pair())
    assert found["BT-1"].rule == found["BT-2"].rule == "REF-SPLIT"
    assert dict(found["BT-1"].lines) == {ONLY_FIRST: None, COMMON: 15000}
    assert dict(found["BT-2"].lines) == {COMMON: None, ONLY_SECOND: None}


def test_each_receipt_shows_the_other_as_its_evidence_and_what_the_other_settles_as_candidates():
    found = proposed(invoices(), pair())
    assert {"kind": "bankLine", "ref": "BT-2"} in found["BT-1"].sources
    assert {"kind": "bankLine", "ref": "BT-1"} in found["BT-2"].sources
    settled_by = {t: {(c["itemId"], c["amountCents"]) for c in found[t].candidates} for t in found}
    assert settled_by["BT-1"] == {(COMMON, 35000), (ONLY_SECOND, 20000)}
    assert settled_by["BT-2"] == {(ONLY_FIRST, 30000), (COMMON, 15000)}


def test_walking_both_in_date_order_the_first_is_partial_and_the_second_closes_what_it_left_open():
    phase = phase_of(invoices(), pair())
    rows, balances = walked(phase, split_invoice.propose(phase, {}))
    assert sorted(rows) == [("BT-1", ONLY_FIRST, 30000, None), ("BT-1", COMMON, 15000, "PARTIAL"),
                            ("BT-2", COMMON, 35000, None), ("BT-2", ONLY_SECOND, 20000, None)]
    assert [balances.open(i) for i in (ONLY_FIRST, COMMON, ONLY_SECOND)] == [0, 0, 0]


def test_one_cent_off_the_sum_of_all_they_cite_settles_nothing():
    assert proposed(invoices(), pair(second_cents=55001)) == {}


def test_two_receipts_citing_only_the_invoice_they_close_are_left_as_they_are_today():
    # The shared risk with ar_instalment and ar_partial: with one invoice there is nothing to split among,
    # so the pass stays out and the line goes on to REF-TEXT, which already leaves it partial and then closes it.
    items = [item(COMMON, "C1", "FA2400022", 50000)]
    txns = [receipt("BT-1", 15000, [COMMON_NUMBER], "2024-06-01"),
            receipt("BT-2", 35000, [COMMON_NUMBER], "2024-06-20")]
    assert proposed(items, txns) == {}
    rows, _ = walked(phase_of(items, txns), {})
    assert rows == [("BT-1", COMMON, 15000, "PARTIAL"), ("BT-2", COMMON, 35000, None)]



def test_a_receipt_with_two_possible_partners_settles_nothing():
    txns = [*pair(), receipt("BT-3", 55000, SECOND, "2024-06-25")]
    assert proposed(invoices(), txns) == {}


def test_two_pairs_over_one_invoice_settle_nothing():
    txns = [*pair(), receipt("BT-3", 40000, FIRST, "2024-07-01"), receipt("BT-4", 60000, SECOND, "2024-07-20")]
    assert proposed(invoices(), txns) == {}


def test_another_customer_citing_the_same_number_is_not_a_partner():
    txns = [receipt("BT-1", 45000, FIRST, "2024-06-01"),
            receipt("BT-2", 55000, SECOND, "2024-06-20", name="Riegos Vallejo S.L.")]
    assert proposed(invoices(), txns) == {}


def test_a_receipt_in_another_currency_is_not_a_partner():
    txns = [receipt("BT-1", 45000, FIRST, "2024-06-01"), receipt("BT-2", 55000, SECOND, "2024-06-20", currency="USD")]
    assert proposed(invoices(), txns) == {}


def test_an_invoice_another_pass_claimed_stops_the_pair(monkeypatch):
    phase = phase_of(invoices(), pair())
    claim = Proposal(rule="ADVICE-CSV", lines=[(ONLY_SECOND, 20000)])
    monkeypatch.setattr(rules, "PASSES", (lambda _: {"BT-9": claim},))
    assert set(rules.propose(phase)) == {"BT-9"}


def test_a_pair_no_other_pass_claimed_comes_out_of_the_rule_passes(monkeypatch):
    monkeypatch.setattr(rules, "PASSES", ())
    assert set(rules.propose(phase_of(invoices(), pair()))) == {"BT-1", "BT-2"}


def test_a_receipt_another_pass_claimed_is_not_a_partner():
    claim = Proposal(rule="ADVICE-CSV", lines=[("ARI-9", 45000)])
    assert proposed(invoices(), pair(), {"BT-1": claim}) == {}


def test_two_invoices_cited_by_both_settle_nothing():
    txns = [receipt("BT-1", 45000, FIRST, "2024-06-01"), receipt("BT-2", 55000, (*FIRST, "FA2400033"), "2024-06-20")]
    assert proposed(invoices(), txns) == {}


def test_a_first_receipt_that_closes_all_it_cites_splits_nothing():
    assert proposed(invoices(), pair(first_cents=80000, second_cents=20000)) == {}


def test_a_first_receipt_that_does_not_reach_the_common_invoice_splits_nothing():
    assert proposed(invoices(), pair(first_cents=30000, second_cents=70000)) == {}


def test_two_receipts_on_one_date_have_no_first_and_settle_nothing():
    assert proposed(invoices(), pair(second_date="2024-06-01")) == {}


def test_an_invoice_issued_after_the_receipt_is_not_what_it_cites():
    items = [*invoices()[:2], item(ONLY_SECOND, "C1", "FA2400033", 20000, issued="2024-06-10")]
    txns = [receipt("BT-1", 45000, (*FIRST, "FA2400033"), "2024-06-01"), receipt("BT-2", 55000, SECOND, "2024-06-20")]
    found = proposed(items, txns)
    assert dict(found["BT-1"].lines) == {ONLY_FIRST: None, COMMON: 15000}


def test_a_name_two_customers_share_is_no_known_customer():
    homonym = ("C3", "E1", "Piscinas Alameda S.L.", None, None, None, None, None)
    assert split_invoice.propose(phase_of(invoices(), pair(), (*CUSTOMERS, homonym)), {}) == {}


def test_an_invoice_already_closed_that_a_receipt_cites_is_left_out():
    items = [*invoices(), item("ARI-4", "C1", "FA2400044", 9000, open_cents=0)]
    txns = [receipt("BT-1", 45000, (*FIRST, "FA2400044"), "2024-06-01"), receipt("BT-2", 55000, SECOND, "2024-06-20")]
    assert dict(proposed(items, txns)["BT-1"].lines) == {ONLY_FIRST: None, COMMON: 15000}


def test_a_receipt_citing_a_credit_note_is_not_this_case():
    items = [*invoices(), item("ARC-1", "C1", "AB2400055", 5000)]
    txns = [receipt("BT-1", 50000, (*FIRST, "AB2400055"), "2024-06-01"), receipt("BT-2", 55000, SECOND, "2024-06-20")]
    assert proposed(items, txns) == {}

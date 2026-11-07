"""REF-SPLIT: two receipts of one customer split the one invoice they both cite.

Why it generalizes: the evidence is on the two bank lines, not in a convention. Both receipts, same customer, entity and
currency, cite one same invoice, and together they are to the cent everything the two cite, open balances. Which invoice
the first left open is then stated by the citations, whichever date or order the invoices have. POLICIES §2 and §3 give
the labels and nothing about the pairing: amount is what was applied, `PARTIAL` while the item stays open, empty for the
remainder after a partial payment.

What is not a clean pair stays with the other rules: anything another pass claimed, one invoice alone (nothing to split
among, REF-TEXT already leaves it partial and closes it), two receipts on one date (no first), two candidate pairs.

Known limit: the pass runs before the walk by date and reads opening balances, so it does not see a third, earlier receipt
that already paid part of these invoices."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations

import polars as pl

from ..load import Phase
from ..model import Proposal
from .party_amount import CREDIT_NOTES, PartyAmount

_COLUMNS = ("bank_txn_id", "booking_date", "amount_cents", "currency", "orig_cents", "orig_currency", "entity", "text",
            "counterparty_name", "counterparty_account", "remittance_info", "ref1", "ref2", "end_to_end_id")


@dataclass(slots=True)
class _Receipt:
    txn_id: str
    date: str
    cash: int
    party: str
    currency: str
    cited: dict[str, int]  # item_id -> open balance


@dataclass(slots=True)
class _Pair:
    first: _Receipt
    second: _Receipt
    common: str
    applied: int  # what the first leaves on the common invoice


def _citing_receipts(phase: Phase, claimed: dict[str, Proposal]) -> list[_Receipt]:
    """Unclaimed receipts of one known customer with the open invoices of their currency they cite, by number or long
    tail. Citing an invoice another pass claimed, or a credit note, takes the receipt out."""
    taken = {item for proposal in claimed.values() for item, _ in proposal.lines}
    opening = dict(zip(phase.items["item_id"].to_list(), phase.items["open_cents"].to_list(), strict=True))
    engine = PartyAmount(phase, reserved={})
    found = []
    for txn in phase.txns.filter(pl.col("amount_cents") > 0).select(_COLUMNS).iter_rows(named=True):
        parties = engine.parties.find(txn, "customer")
        if txn["bank_txn_id"] in claimed or len(parties) != 1:
            continue
        cash, currency = engine._cash(txn)
        issued = [i for i in engine.items.get(parties[0], ()) if i[3] == currency and i[2] <= txn["booking_date"]
                  and opening[i[0]] > 0]
        strong, _ = engine._cited(issued, engine._tokens(txn))
        cited = {i[0]: opening[i[0]] for i in strong}
        if cited and not cited.keys() & taken and not any(i[:3] in CREDIT_NOTES for i in cited):
            found.append(_Receipt(txn["bank_txn_id"], txn["booking_date"], cash, parties[0], currency, cited))
    engine.release()
    return found


def _pairs_of(receipts: list[_Receipt]) -> list[_Pair]:
    """An invoice has one customer, entity and currency: two receipts citing it share them."""
    citing: dict[str, list[_Receipt]] = defaultdict(list)
    for receipt in receipts:
        for item in receipt.cited:
            citing[item].append(receipt)
    pairs = []
    for common, group in citing.items():
        for one, other in combinations(group, 2):
            first, second = sorted((one, other), key=lambda r: r.date)
            everything = {**first.cited, **second.cited}
            if first.date == second.date or first.cited.keys() & second.cited.keys() != {common} or len(everything) < 2:
                continue
            if first.cash + second.cash != sum(everything.values()) or first.cash >= sum(first.cited.values()):
                continue
            applied = first.cash - sum(o for i, o in first.cited.items() if i != common)
            if applied > 0:
                pairs.append(_Pair(first, second, common, applied))
    return pairs


def _proposal(receipt: _Receipt, other: _Receipt, lines: list[tuple[str, int | None]],
              other_settles: dict[str, int]) -> Proposal:
    why = f"settled by {other.txn_id}"
    return Proposal(
        rule="REF-SPLIT", lines=lines, confidence=0.9, party_id=receipt.party,
        sources=[{"kind": "bankLine", "ref": other.txn_id}, {"kind": "customer", "ref": receipt.party}],
        candidates=[{"itemId": i, "amountCents": cents, "currency": receipt.currency, "why": why}
                    for i, cents in sorted(other_settles.items())])


def propose(phase: Phase, claimed: dict[str, Proposal]) -> dict[str, Proposal]:
    """Runs after the passes, whose claims it needs. A receipt or an invoice in two candidate pairs settles nothing."""
    pairs = _pairs_of(_citing_receipts(phase, claimed))
    uses: Counter = Counter()
    for p in pairs:
        uses.update({p.first.txn_id, p.second.txn_id, *p.first.cited, *p.second.cited})
    proposals: dict[str, Proposal] = {}
    for p in pairs:
        if any(uses[key] > 1 for key in (p.first.txn_id, p.second.txn_id, *p.first.cited, *p.second.cited)):
            continue
        own = {i: o for i, o in p.first.cited.items() if i != p.common}
        rest = {i: o for i, o in p.second.cited.items() if i != p.common}
        open_common = p.first.cited[p.common]
        proposals[p.first.txn_id] = _proposal(
            p.first, p.second, [*((i, None) for i in sorted(own)), (p.common, p.applied)],
            {**rest, p.common: open_common - p.applied})
        proposals[p.second.txn_id] = _proposal(
            p.second, p.first, [(i, None) for i in sorted({p.common, *rest})], {**own, p.common: p.applied})
    return proposals

"""A third party pays for the customer, inside one entity: a collection agency, a confirming bank, a factor (POLICIES
§5.1: "a collection agency may pay old invoices").

Why it generalizes: the official example says "La agencia paga por cuenta del cliente: el ordenante no es cliente, pero
el concepto nombra al deudor o la factura". No agency is listed: what counts is an ordering party the masters do not
know and a text that identifies one open invoice, to the cent. A receipt with the amount and neither of the two remains
UNIDENTIFIED (POLICIES §3: "Do not force a match").
"""
from __future__ import annotations

import re
from itertools import combinations

from ..model import Proposal
from ..state import OpenBalances
from .ar_common import MIN_SUFFIX

_DIGITS = re.compile(rf"\d{{{MIN_SUFFIX},}}")
MAX_OPEN = 60  # open invoices of the debtor beyond which the triples are too many to search
_FIELDS = ("text", "remittance_info", "ref1", "ref2", "end_to_end_id")


def tail_key(digits: str) -> str | None:
    """The key of an invoice in `PartyAmount.by_tail`: a tail shorter than this cites nothing."""
    return digits[-MIN_SUFFIX:] if len(digits) >= MIN_SUFFIX else None


def paid_by_agency(engine, txn: dict, cash: int, currency: str, balances: OpenBalances) -> Proposal | None:
    """A receipt no customer ordered: the one open invoice of the cash that its text cites, else that it names."""

    def pays(item: tuple) -> bool:
        return (item[0][:3] == "ARI" and item[3] == currency and item[2] <= txn["booking_date"]
                and balances.open(item[0]) == cash and engine.is_free(item, cash, balances))

    entity = txn["entity"]
    text = " | ".join(filter(None, (txn[field] for field in _FIELDS)))
    cited = {}
    for run in _DIGITS.findall(text):
        tail = run.lstrip("0")
        for party, item in engine.by_tail.get((entity, tail_key(tail)), ()):
            if item[7].endswith(tail) and pays(item):
                cited[item[0]] = (party, item)
    if len(cited) == 1:
        return _settles("REF-AGENCY", *next(iter(cited.values())), txn)
    named = engine.parties.named_in(text, entity)
    exact = [(party, item) for party in named for item in engine.items.get(party, ()) if pays(item)]
    if len(exact) == 1:
        return _settles("PARTY-AGENCY", *exact[0], txn)
    return _old_invoices(engine, txn, cash, currency, balances, named) if len(named) == 1 and not exact else None


def _old_invoices(engine, txn: dict, cash: int, currency: str, balances: OpenBalances, named) -> Proposal | None:
    """POLICIES §5.1: the agency pays several old invoices of the debtor it names. Only a unique set of two or three
    open invoices summing to the cent is taken."""
    party = next(iter(named))
    items = [item for item in engine.items.get(party, ())
             if item[0][:3] == "ARI" and item[3] == currency and item[2] <= txn["booking_date"]
             and 0 < balances.open(item[0]) < cash and engine.is_free(item, balances.open(item[0]), balances)]
    if len(items) > MAX_OPEN:
        return None
    found = [combo for size in (2, 3) for combo in combinations(items, size)
             if sum(balances.open(item[0]) for item in combo) == cash]
    if len(found) != 1:
        return None
    sources = [{"kind": "customer", "ref": party}, {"kind": "bankLine", "ref": txn["bank_txn_id"]}]
    return Proposal("PARTY-AGENCY-SET", [(item[0], None) for item in found[0]], confidence=0.8, party_id=party,
                    sources=sources)


def _settles(rule: str, party: str, item: tuple, txn: dict) -> Proposal:
    sources = [{"kind": "customer", "ref": party}, {"kind": "bankLine", "ref": txn["bank_txn_id"]}]
    return Proposal(rule, [(item[0], None)], confidence=0.9, party_id=party, reference=item[1], sources=sources)

"""A collection agency pays for the customer, inside one entity (POLICIES §5.1: "a collection agency may pay old
invoices").

Why it generalizes: the official example says "La agencia paga por cuenta del cliente: el ordenante no es cliente, pero
el concepto nombra al deudor o la factura". No agency is listed: what counts is an ordering party the masters do not
know and a text that identifies one open invoice, to the cent. A receipt with the amount and neither of the two remains
UNIDENTIFIED (POLICIES §3: "Do not force a match").
"""
from __future__ import annotations

import re

from ..model import Proposal
from ..state import OpenBalances
from .ar_common import MIN_SUFFIX

_DIGITS = re.compile(rf"\d{{{MIN_SUFFIX},}}")
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
    return _settles("PARTY-AGENCY", *exact[0], txn) if len(exact) == 1 else None


def _settles(rule: str, party: str, item: tuple, txn: dict) -> Proposal:
    sources = [{"kind": "customer", "ref": party}, {"kind": "bankLine", "ref": txn["bank_txn_id"]}]
    return Proposal(rule, [(item[0], None)], confidence=0.9, party_id=party, reference=item[1], sources=sources)

"""REF-SETTLEMENT: a line that pays exactly what an earlier deduction left open on the one invoice it cites.

Why it generalizes: POLICIES §3 says the disputed part "may be paid later → that later line has no exception". The
official example of `ar_short_dispute` shows the other half: the row with the deduction carries what was paid, so the
rest stays open. The evidence is structural, in no language: the invoice's own history has a SHORT_DISPUTE, the balance
it left is the cash to the cent, and the line cites that invoice by its complete number. It goes before the search by
party because a subset of smaller invoices can also add up to such a small amount.

Not claimed: several invoices cited, a balance no dispute left, a cash that is not the whole balance. Known limit: when
the earlier line went unseen there is no history, and the line stays with the other rules."""
from __future__ import annotations

from ..model import Proposal
from .party_amount import PartyAmount, _alnum


class Settling(PartyAmount):
    def __call__(self, txn: dict, balances) -> Proposal | None:
        return self._settled(txn, balances) or super().__call__(txn, balances)

    def _settled(self, txn: dict, balances) -> Proposal | None:
        if txn["amount_cents"] <= 0:
            return None
        cited = {entry[0]: entry for token in self._tokens(txn)
                 for entry in self.by_number.get((txn["entity"], _alnum(token)), ()) if entry[0].startswith("ARI")}
        if len(cited) != 1:
            return None
        (item_id, entry), = cited.items()
        cash, currency = self._cash(txn)
        if entry[3] != currency or balances.open(item_id) != cash:
            return None
        disputed = [m["bankTxnId"] for m in balances.history(item_id) if m["exception"] == "SHORT_DISPUTE"]
        if not disputed:
            return None
        return Proposal(rule="REF-SETTLEMENT", lines=[(item_id, None)], reference=entry[1],
                        sources=[{"kind": "bankLine", "ref": disputed[0]}])

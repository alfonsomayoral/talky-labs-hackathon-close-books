"""Walk the bank lines by booking date, apply the best proposal, fix amount and exception, update balances."""
from __future__ import annotations

from .categories import fallback
from .load import Phase
from .model import Proposal, Row
from .policy import decide
from .state import OpenBalances


def resolve(phase: Phase, proposals: dict[str, Proposal]) -> tuple[list[Row], OpenBalances]:
    items = phase.items
    balances = OpenBalances(dict(zip(items["item_id"].to_list(), items["open_cents"].to_list(), strict=True)))
    currency = dict(zip(items["item_id"].to_list(), items["currency"].to_list(), strict=True))
    rows: list[Row] = []
    for txn in phase.txns.select(
        "bank_txn_id", "booking_date", "amount_cents", "currency", "bank", "bank_code", "bank_subcode", "text"
    ).iter_rows(named=True):
        txn_id = txn["bank_txn_id"]
        proposal = proposals.get(txn_id)
        if proposal is None:
            out = fallback(txn)
            rows.append(Row(txn_id, None, None, None, out.category, out.exception or None, out.rule, out.confidence))
            continue
        for item_id, applied in proposal.lines:
            amount, exception = decide(balances.open(item_id), applied)
            balances.apply(item_id, amount, exception, txn_id, txn["booking_date"])
            rows.append(Row(txn_id, item_id, amount, currency[item_id], None, exception or None, proposal.rule,
                            proposal.confidence, proposal.party_id, proposal.reference, proposal.sources,
                            proposal.candidates))
    return rows, balances

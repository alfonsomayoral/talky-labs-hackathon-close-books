"""Rules in passes of certainty (PLAN §2.2). A bank line keeps the proposal of the first rule that claims it."""
from __future__ import annotations

from ..load import Phase
from ..model import Proposal
from . import advices, card_settlements, categories, cheque_deposits, dd_batches, payment_runs, split_invoice
from .dispute_settlement import Settling
from .party_amount import PartyAmount

PASSES = (
    payment_runs.propose,
    advices.propose,
    dd_batches.propose,
    card_settlements.propose,
    cheque_deposits.propose,
    categories.propose,
)


def propose(phase: Phase) -> dict[str, Proposal]:
    proposals: dict[str, Proposal] = {}
    for rule in PASSES:
        for txn_id, proposal in rule(phase).items():
            proposals.setdefault(txn_id, proposal)
    return {**proposals, **split_invoice.propose(phase, proposals)}


def stateful(phase: Phase, proposals: dict[str, Proposal]) -> PartyAmount:
    """What needs the balance at each date: runs inside resolve on the lines no pass claimed."""
    reserved: dict[str, set[str]] = {}
    for txn_id, proposal in proposals.items():
        for item, _ in proposal.lines:
            reserved.setdefault(item, set()).add(txn_id)
    return Settling(phase, reserved)

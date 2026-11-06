"""Rules in passes of certainty (PLAN §2.2). A bank line keeps the proposal of the first rule that claims it."""
from __future__ import annotations

from ..load import Phase
from ..model import Proposal
from . import card_settlements, categories, dd_batches, payment_runs

PASSES = (payment_runs.propose, dd_batches.propose, card_settlements.propose, categories.propose)


def propose(phase: Phase) -> dict[str, Proposal]:
    proposals: dict[str, Proposal] = {}
    for rule in PASSES:
        for txn_id, proposal in rule(phase).items():
            proposals.setdefault(txn_id, proposal)
    return proposals

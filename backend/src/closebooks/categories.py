"""Lines that settle no item (POLICIES §4)."""
from __future__ import annotations

from typing import NamedTuple


class NoItem(NamedTuple):
    category: str
    exception: str
    rule: str
    confidence: float


def fallback(txn: dict) -> NoItem:
    """No evidence: a receipt is UNIDENTIFIED (never forced); a debit gets its category."""
    if txn["amount_cents"] > 0:
        return NoItem("UNIDENTIFIED", "UNIDENTIFIED", "FALLBACK-UNIDENTIFIED", 0.0)
    return NoItem("BANK_FEES", "", "FALLBACK-CATEGORY", 0.0)

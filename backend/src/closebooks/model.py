"""What rules propose and what resolve emits."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Proposal:
    """Which items a bank line settles. A rule never decides the final amount or exception."""

    rule: str
    lines: list[tuple[str, int | None]]  # (item_id, cash applied in item currency if a document says so)
    confidence: float = 1.0
    party_id: str | None = None
    reference: str | None = None
    sources: list[dict] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)


@dataclass(slots=True)
class Row:
    bank_txn_id: str
    item_id: str | None
    amount_cents: int | None
    currency: str | None
    category: str | None
    exception: str | None
    rule: str
    confidence: float
    party_id: str | None = None
    reference: str | None = None
    sources: list[dict] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)

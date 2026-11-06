"""Amount and exception of each row (POLICIES §2-§3), in one place whichever rule produced the match."""
from __future__ import annotations

CREDIT_NOTES = ("ARC", "APC")


def decide(item_id: str, item_currency: str, txn_currency: str, open_cents: int, applied_cents: int | None,
           returned: bool = False) -> tuple[int, str]:
    if returned:
        return (applied_cents if applied_cents is not None else open_cents), "RETURNED"
    if open_cents <= 0:
        return (applied_cents if applied_cents is not None else 0), "DUPLICATE_PAYMENT"
    if applied_cents is not None and applied_cents < open_cents:
        return applied_cents, "PARTIAL"
    if item_currency != txn_currency and item_id[:3] not in CREDIT_NOTES:
        return open_cents, "FX_DIFFERENCE"
    return open_cents, ""

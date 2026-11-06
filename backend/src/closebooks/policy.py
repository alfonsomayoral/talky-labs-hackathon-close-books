"""Amount and exception of each row (POLICIES §2-§3), in one place whichever rule produced the match."""
from __future__ import annotations


def decide(open_cents: int, applied_cents: int | None) -> tuple[int, str]:
    if applied_cents is None:
        return open_cents, ""
    return applied_cents, ""

"""Open balance per item and its settlement history, kept in booking-date order by resolve."""
from __future__ import annotations

from collections import defaultdict

NO_BALANCE_EFFECT = {"DUPLICATE_PAYMENT"}


class OpenBalances:
    def __init__(self, opening: dict[str, int], totals: dict[str, int] | None = None):
        self._open = opening
        self._totals = totals or {}
        self._history: dict[str, list[dict]] = defaultdict(list)

    def open(self, item_id: str) -> int:
        return self._open[item_id]

    def apply(self, item_id: str, amount_cents: int, exception: str, txn_id: str, booking_date: str) -> None:
        if exception == "RETURNED":
            # The payment returned may predate the data: the balance can never exceed the document.
            reopened = self._open[item_id] + amount_cents
            self._open[item_id] = min(reopened, self._totals.get(item_id, reopened))
        elif exception not in NO_BALANCE_EFFECT:
            self._open[item_id] -= amount_cents
        self._history[item_id].append(
            {"bankTxnId": txn_id, "bookingDate": booking_date, "amountCents": amount_cents, "exception": exception})

    def history(self, item_id: str) -> list[dict]:
        return self._history.get(item_id, [])

    def touched(self) -> dict[str, list[dict]]:
        return self._history

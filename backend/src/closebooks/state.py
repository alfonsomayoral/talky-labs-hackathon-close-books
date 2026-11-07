"""Open balance per item and its settlement history, kept in booking-date order by resolve."""
from __future__ import annotations

from array import array
from collections import defaultdict
from collections.abc import KeysView

import polars as pl

NO_BALANCE_EFFECT = {"DUPLICATE_PAYMENT"}


class OpenBalances:
    def __init__(self, opening: dict[str, int], totals: dict[str, int] | None = None):
        self.index = {item: i for i, item in enumerate(opening)}
        self._open = array("q", opening.values())
        self._totals: array | list[int | None] | None = [totals.get(item) for item in opening] if totals else None
        self._history: dict[str, list[tuple[str, str, int, str]]] = defaultdict(list)

    @classmethod
    def from_items(cls, items: pl.DataFrame) -> OpenBalances:
        """One shared id index and int64 vectors; do not build a Python dictionary for each column."""
        balances = cls({})
        balances.index = {item: i for i, item in enumerate(items["item_id"])}
        balances._open = array("q", items["open_cents"])
        balances._totals = array("q", items["total_cents"])
        return balances

    def open(self, item_id: str) -> int:
        return self._open[self.index[item_id]]

    def total(self, item_id: str) -> int | None:
        return self._totals[self.index[item_id]] if self._totals is not None else None

    def apply(self, item_id: str, amount_cents: int, exception: str, txn_id: str, booking_date: str) -> None:
        i = self.index[item_id]
        if exception == "RETURNED":
            # The payment returned may predate the data: the balance can never exceed the document.
            reopened = self._open[i] + amount_cents
            total = self._totals[i] if self._totals is not None else None
            self._open[i] = min(reopened, total) if total is not None else reopened
        elif exception not in NO_BALANCE_EFFECT:
            self._open[i] -= amount_cents
        self._history[item_id].append((txn_id, booking_date, amount_cents, exception))

    def history(self, item_id: str) -> list[dict]:
        return [{"bankTxnId": txn, "bookingDate": booked, "amountCents": amount, "exception": exception}
                for txn, booked, amount, exception in self._history.get(item_id, ())]

    def touched(self) -> KeysView[str]:
        return self._history.keys()

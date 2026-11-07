"""Open balance per item and its settlement history, kept in booking-date order by resolve."""
from __future__ import annotations

from array import array
from collections.abc import Iterator

import polars as pl

NO_BALANCE_EFFECT = {"DUPLICATE_PAYMENT"}


class ItemColumn:
    """Repeated labels as uint32 codes, with fast scalar access."""

    def __init__(self, column: pl.Series):
        labels = column.drop_nulls().unique(maintain_order=True)
        self.values = [*labels, None]
        self.codes = array("I", column.cast(pl.Enum(labels)).to_physical().fill_null(len(labels)))

    def __getitem__(self, index: int) -> str | None:
        return self.values[self.codes[index]]


class OpenBalances:
    def __init__(self, opening: dict[str, int], totals: dict[str, int] | None = None):
        self.index = {item: i for i, item in enumerate(opening)}
        self._open = array("q", opening.values())
        self._totals: array | list[int | None] | None = [totals.get(item) for item in opening] if totals else None
        self._init_history(len(self.index))

    def _init_history(self, size: int) -> None:
        self._first = array("i", [-1]) * size
        self._last = array("i", [-1]) * size
        self._next = array("i")
        self._amounts = array("q")
        self._event_txns = array("I")
        self._event_exceptions = array("B")
        self._txn_ids: list[str] = []
        self._txn_dates: list[str] = []
        self._dates: dict[str, str] = {}
        self._exceptions: list[str] = []
        self._exception_codes: dict[str, int] = {}

    @classmethod
    def from_items(cls, items: pl.DataFrame) -> OpenBalances:
        """One shared id index and int64 vectors; do not build a Python dictionary for each column."""
        balances = cls({})
        balances.index = {item: i for i, item in enumerate(items["item_id"])}
        balances._open = array("q", items["open_cents"])
        balances._totals = array("q", items["total_cents"])
        balances._init_history(items.height)
        return balances

    def open(self, item_id: str) -> int:
        return self._open[self.index[item_id]]

    def open_at(self, position: int) -> int:
        return self._open[position]

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
        event = len(self._amounts)
        if not self._txn_ids or self._txn_ids[-1] != txn_id or self._txn_dates[-1] != booking_date:
            self._txn_ids.append(txn_id)
            self._txn_dates.append(self._dates.setdefault(booking_date, booking_date))
        if exception not in self._exception_codes:
            self._exception_codes[exception] = len(self._exceptions)
            self._exceptions.append(exception)
        self._amounts.append(amount_cents)
        self._event_txns.append(len(self._txn_ids) - 1)
        self._event_exceptions.append(self._exception_codes[exception])
        self._next.append(-1)
        previous = self._last[i]
        if previous >= 0:
            self._next[previous] = event
        else:
            self._first[i] = event
        self._last[i] = event

    def history(self, item_id: str) -> list[dict]:
        event = self._first[self.index[item_id]] if item_id in self.index else -1
        history = []
        while event >= 0:
            txn = self._event_txns[event]
            history.append({"bankTxnId": self._txn_ids[txn], "bookingDate": self._txn_dates[txn],
                            "amountCents": self._amounts[event],
                            "exception": self._exceptions[self._event_exceptions[event]]})
            event = self._next[event]
        return history

    def has_history(self, item_id: str) -> bool:
        return self._first[self.index[item_id]] >= 0

    def touched(self) -> Iterator[str]:
        return (item for item, index in self.index.items() if self._first[index] >= 0)

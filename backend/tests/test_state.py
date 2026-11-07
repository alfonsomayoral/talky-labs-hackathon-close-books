from __future__ import annotations

import tracemalloc

import polars as pl

from closebooks.state import OpenBalances


def test_settlement_history_uses_compact_events_instead_of_a_python_tuple_per_allocation():
    balances = OpenBalances({"ARI-1": 0})
    tracemalloc.start()
    try:
        for _ in range(100_000):
            balances.apply("ARI-1", 1234, "DUPLICATE_PAYMENT", "BT-1", "2025-01-01")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 4 * 1024**2, f"settlement history allocated {peak / 1024**2:.1f} MiB"
    history = balances.history("ARI-1")
    assert len(history) == 100_000
    assert history[0] == history[-1] == {
        "bankTxnId": "BT-1", "bookingDate": "2025-01-01", "amountCents": 1234, "exception": "DUPLICATE_PAYMENT"}
    assert balances.open("ARI-1") == 0


def test_column_balances_keep_large_cents_and_ordered_history_through_duplicates_and_returns():
    items = pl.DataFrame({"item_id": ["ARI-1", "ARI-2"], "open_cents": [4_000_000_000, 0],
                          "total_cents": [5_000_000_000, 800]})
    balances = OpenBalances.from_items(items)
    assert balances.total("ARI-1") == 5_000_000_000
    balances.apply("ARI-1", 4_000_000_000, "", "BT-1", "2025-01-01")
    balances.apply("ARI-1", 4_000_000_000, "DUPLICATE_PAYMENT", "BT-2", "2025-01-02")
    assert balances.open("ARI-1") == 0
    balances.apply("ARI-1", 6_000_000_000, "RETURNED", "BT-3", "2025-01-03")
    assert balances.open("ARI-1") == 5_000_000_000
    assert balances.open_at(balances.index["ARI-1"]) == 5_000_000_000
    assert balances.total("ARI-1") == 5_000_000_000
    assert balances.open("ARI-2") == 0
    assert set(balances.touched()) == {"ARI-1"}
    assert balances.history("ARI-1") == [
        {"bankTxnId": "BT-1", "bookingDate": "2025-01-01", "amountCents": 4_000_000_000, "exception": ""},
        {"bankTxnId": "BT-2", "bookingDate": "2025-01-02", "amountCents": 4_000_000_000,
         "exception": "DUPLICATE_PAYMENT"},
        {"bankTxnId": "BT-3", "bookingDate": "2025-01-03", "amountCents": 6_000_000_000,
         "exception": "RETURNED"},
    ]
    assert balances.history("ARI-2") == []
    assert set(balances.touched()) == {"ARI-1"}
    assert items["open_cents"].to_list() == [4_000_000_000, 0]

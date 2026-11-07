"""Factura menos su abono como unidad en la búsqueda sin cita. Casos inventados."""
from __future__ import annotations

from test_party_amount import engine, item

from closebooks.rules.note_unit import note_units


def settle(rows, cash, party="C1"):
    rule, balances = engine(rows)
    free = [(i, balances.open(i[0])) for i in rule.items[party] if rule.is_free(i, balances.open(i[0]), balances)]
    found = note_units(free, cash, rule.credits)
    return None if found is None else set(found)


def test_an_invoice_less_the_note_that_names_it_gives_a_row_for_each():
    rows = [item("ARI-1", "C1", "F1", 100000), item("ARC-1", "C1", "N1", 20000, related="F1")]
    assert settle(rows, 80000) == {("ARI-1", 100000), ("ARC-1", 20000)}


def test_a_unit_goes_with_a_loose_invoice():
    rows = [item("ARI-1", "C1", "F1", 100000), item("ARC-1", "C1", "N1", 20000, related="F1"),
            item("ARI-2", "C1", "F2", 50000)]
    assert settle(rows, 130000) == {("ARI-1", 100000), ("ARC-1", 20000), ("ARI-2", 50000)}


def test_a_note_that_names_nothing_is_no_unit():
    rows = [item("ARI-1", "C1", "F1", 100000), item("ARC-1", "C1", "N1", 20000)]
    assert settle(rows, 80000) is None


def test_a_loose_note_cannot_close_the_sum_of_other_invoices():
    rows = [item("ARI-1", "C1", "F1", 100000), item("ARI-2", "C1", "F2", 50000), item("ARC-1", "C1", "N1", 30000)]
    assert settle(rows, 120000) is None


def test_two_sets_with_the_same_sum_settle_nothing():
    rows = [item("ARI-1", "C1", "F1", 100000), item("ARC-1", "C1", "N1", 20000, related="F1"),
            item("ARI-2", "C1", "F2", 90000), item("ARC-2", "C1", "N2", 10000, related="F2")]
    assert settle(rows, 80000) is None


def test_the_invoice_alone_ties_with_its_unit():
    # 80000 + 70000 with the note, or 100000 + 50000 leaving the note open: the cash does not say which.
    rows = [item("ARI-1", "C1", "F1", 100000), item("ARC-1", "C1", "N1", 20000, related="F1"),
            item("ARI-2", "C1", "F2", 70000), item("ARI-3", "C1", "F3", 50000)]
    assert settle(rows, 150000) is None


def test_an_invoice_is_not_counted_alone_and_in_its_unit_at_once():
    rows = [item("ARI-1", "C1", "F1", 100000), item("ARC-1", "C1", "N1", 20000, related="F1")]
    assert settle(rows, 180000) is None


def test_a_note_of_an_invoice_no_longer_open_is_no_unit():
    rows = [item("ARI-1", "C1", "F1", 100000, open_cents=0), item("ARC-1", "C1", "N1", 20000, related="F1")]
    assert settle(rows, 80000) is None


def test_a_note_naming_an_invoice_of_another_party_is_no_unit():
    rows = [item("ARI-1", "C2", "F1", 100000), item("ARC-1", "C1", "N1", 20000, related="F1")]
    assert settle(rows, 80000) is None


def test_a_fully_credited_invoice_does_not_block_the_others():
    rows = [item("ARI-1", "C1", "F1", 50000), item("ARC-1", "C1", "N1", 50000, related="F1"),
            item("ARI-2", "C1", "F2", 100000), item("ARI-3", "C1", "F3", 30000)]
    assert settle(rows, 130000) == {("ARI-2", 100000), ("ARI-3", 30000)}


def test_currencies_are_never_added():
    rows = [item("ARI-1", "C1", "F1", 100000), item("ARC-1", "C1", "N1", 20000, related="F1"),
            item("ARI-2", "C1", "F2", 50000, currency="USD")]
    assert settle(rows, 130000) is None


def test_the_search_bound_counts_what_is_searched_not_the_loose_notes():
    rows = [item(f"ARI-{k}", "C1", f"F{k}", 1000 << k) for k in range(22)]
    cash = sum(1000 << k for k in range(22))
    assert settle([*rows, item("ARC-1", "C1", "N1", 500)], cash) == {(r["item_id"], r["total_cents"]) for r in rows}
    assert settle([*rows, item("ARI-X", "C1", "FX", 1000 << 22)], cash + (1000 << 22)) is None


def test_a_set_that_chance_explains_proves_nothing():
    rows = [item("ARI-1", "C1", "F1", 10), item("ARI-2", "C1", "F2", 20)]
    assert settle(rows, 30) is None

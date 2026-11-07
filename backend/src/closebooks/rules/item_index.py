"""Columnar invoices, compact reference indexes and balance filtering before materializing records."""
from __future__ import annotations

import re
from array import array
from bisect import bisect_left, bisect_right
from collections import defaultdict

import polars as pl

from ..state import ItemColumn, OpenBalances

MIN_SUFFIX = 3
STRONG_SUFFIX = 5
MIN_CUT = 6


class _HashIndex:
    """Hashes locate candidates; callers verify the original fields, including hash collisions."""

    def __init__(self, rows):
        hashes, positions = array("q"), array("I")
        for left, right, position in rows:
            hashes.append(hash((left, right)))
            positions.append(position)
        ordered = pl.DataFrame({"hash": pl.Series(hashes), "position": pl.Series(positions)}).sort("hash", "position")
        self.hashes = array("q", ordered["hash"])
        self.positions = array("I", ordered["position"])

    def find(self, left: str, right: str):
        key = hash((left, right))
        return (self.positions[n] for n in range(bisect_left(self.hashes, key), bisect_right(self.hashes, key)))


class ItemIndex:
    def __init__(self, items: pl.DataFrame, cancelled: set[str], replaced: dict[str, str]):
        known = items.select("item_id", "party_id", "document_number", "issue_date", "currency", "total_cents",
                             "customer_po", "entity").with_row_index("_balance_row").filter(
                                 pl.col("party_id").is_not_null())
        if cancelled:
            known = known.filter(~pl.col("item_id").is_in(list(cancelled)))
        known = known.with_row_index("_row").with_columns(
            pl.col("document_number").fill_null("").alias("document_number"),
            pl.col("issue_date").fill_null("").alias("issue_date"),
            pl.col("customer_po").fill_null("").str.to_uppercase().alias("customer_po"),
        ).with_columns(
            pl.col("document_number").str.to_uppercase().str.replace_all(r"[^A-Z0-9]", "").alias("_compact"),
            pl.col("document_number").str.replace_all(r"\D", "").alias("_digits"))
        self.rows = known.select("item_id", "document_number", "issue_date", "currency", "total_cents",
                                 "customer_po", "_compact", "_digits", "entity", "party_id")
        self.compacts = known["_compact"].to_list()
        self.issued, self.currencies = ItemColumn(known["issue_date"]), ItemColumn(known["currency"])
        self.balance_positions = array("I", known["_balance_row"])
        self._reserved_flags: bytearray | None = None
        self.replaced = replaced
        self.parties = {party: array("I", positions) for party, positions in
                        known.group_by("party_id", maintain_order=True).agg("_row").iter_rows()}
        self.by_entity = _HashIndex(known.filter(pl.col("_compact").str.len_chars() >= MIN_CUT)
                                    .select("entity", "_compact", "_row").iter_rows())
        self.exact = _HashIndex(known.select("party_id", "_compact", "_row").iter_rows())
        self.prefix = _HashIndex(known.select("party_id", pl.col("_compact").str.slice(0, MIN_CUT), "_row").iter_rows())
        self.suffix = _HashIndex(known.select("party_id", pl.col("_digits").str.slice(-MIN_SUFFIX), "_row").iter_rows())
        self.po = _HashIndex(known.filter(pl.col("customer_po") != "")
                             .select("party_id", "customer_po", "_row").iter_rows())
        self.replacement_refs: dict[tuple[str, str], list[int]] = defaultdict(list)
        if replaced:
            for item, party, position in known.filter(pl.col("item_id").is_in(list(replaced))) \
                    .select("item_id", "party_id", "_row").iter_rows():
                self.replacement_refs[party, replaced[item]].append(position)

    def free(self, party: str, date: str, currency: str, balances: OpenBalances, reserved: set[str],
             unknown_before: str) -> list[tuple]:
        if self._reserved_flags is None:
            self._reserved_flags = bytearray(len(balances.index))
            for item_id in reserved:
                self._reserved_flags[balances.index[item_id]] = 1
        found = []
        for position in self.parties.get(party, ()):
            issued = self.issued[position]
            if issued > date or issued < unknown_before or self.currencies[position] != currency:
                continue
            balance_position = self.balance_positions[position]
            if not self._reserved_flags[balance_position] and (amount := balances.open_at(balance_position)) > 0:
                found.append((self._entry(position), amount))
        return found

    def number(self, entity: str, compact: str) -> list[tuple]:
        return [self._entry(position) for position in self.by_entity.find(entity, compact)
                if (row := self.rows.row(position))[8] == entity and row[6] == compact]

    def _entry(self, position: int) -> tuple:
        row = self.rows.row(position)
        return (*row[:8], self.replaced.get(row[0], ""))

    def cited(self, party: str, tokens: set[str], date: str, currency: str) -> tuple[list[tuple], list[tuple]]:
        levels: dict[int, int] = {}
        for token in tokens:
            flat = re.sub(r"[^A-Z0-9]", "", token.upper())
            if len(flat) < MIN_SUFFIX:
                continue
            for position in self.exact.find(party, flat):
                if self.compacts[position] == flat:
                    levels[position] = 2
            for position in self.po.find(party, token):
                if self.rows.row(position)[5] == token:
                    levels[position] = 2
            for position in self.replacement_refs.get((party, flat), ()):
                levels[position] = 2
            core = flat.lstrip("0") or flat
            if flat.isdigit() and len(core) >= MIN_SUFFIX:
                level = 2 if len(core) >= STRONG_SUFFIX else 1
                for position in self.suffix.find(party, core[-MIN_SUFFIX:]):
                    if self.rows.row(position)[7].endswith(core):
                        levels[position] = max(levels.get(position, 0), level)
            if len(flat) >= MIN_CUT:
                for position in self.prefix.find(party, flat[:MIN_CUT]):
                    if self.compacts[position].startswith(flat):
                        levels[position] = max(levels.get(position, 0), 1)
        strong, weak = [], []
        for position in sorted(levels):
            row = self.rows.row(position)
            if row[9] == party and row[2] <= date and row[3] == currency:
                (strong if levels[position] == 2 else weak).append(self._entry(position))
        return strong, weak

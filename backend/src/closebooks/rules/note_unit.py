"""An invoice less the open credit notes that name it, as one unit of the search of a cash that cites nothing."""
from __future__ import annotations

from collections import defaultdict

from ..policy import CREDIT_NOTES, MAX_CHANCE
from .party_amount import MAX_FULL_SEARCH, _chance, _unique_subset


def note_units(free: list, cash: int, credits: dict[str, str]) -> list[tuple[str, int]] | None:
    """The only set of invoices, each alone or as a unit, that adds up to the cash: (item, open cents) by item.

    `free` is what `_subset` takes, the open items of one party, and a party belongs to one entity in the masters. A
    credit note never goes in by itself. An invoice can also be paid leaving its note open, so it is searched both ways:
    that reading can only tie with a unit and leave the line with nothing, never force one."""
    if len({i[3] for i, _ in free}) > 1:
        return None
    ordered = sorted(free, key=lambda x: (x[0][2], x[0][0]))
    invoices = [x for x in ordered if x[0][0][:3] not in CREDIT_NOTES]
    by_number = defaultdict(list)
    for invoice, _ in invoices:
        by_number[invoice[6]].append(invoice[0])
    notes = defaultdict(list)
    for note, open_cents in ordered:
        named = by_number.get(credits.get(note[0], ""), ())
        if note[0][:3] in CREDIT_NOTES and len(named) == 1:
            notes[named[0]].append((note[0], open_cents))
    searched = []
    for invoice, open_cents in invoices:
        searched.append(((invoice[0],), open_cents))
        if own := notes.get(invoice[0]):
            searched.append(((invoice[0], *(n for n, _ in own)), open_cents - sum(o for _, o in own)))
    searched = [(unit, value) for unit, value in searched if 0 < value <= cash]
    if len(searched) > MAX_FULL_SEARCH or _chance(2 ** len(searched), [v for _, v in searched]) > MAX_CHANCE:
        return None
    chosen = _unique_subset(searched, cash, 1)
    items = [i for unit in chosen or () for i in unit]
    if not items or len(set(items)) != len(items):  # an invoice both alone and in its unit is no set
        return None
    opens = {i[0]: o for i, o in free}
    return [(i, opens[i]) for i in items]

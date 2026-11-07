"""PARTY-WITHHELD-SET, REF-WITHHELD-SET: a customer seen withholding at a rate pays one set of invoices net of it.

This is an inference, and the rows say so (Evidence.SEEN_RATE, review). POLICIES §3 says only "some" customers of
Mexico, Brazil and Morocco withhold, at 1.25 %, 1.5 % or 10 % of the invoice total. The country is the master's and the
rates are the policy's. Who withholds, and at which rate, comes from this run: an earlier line of the customer whose
cash is its invoices net of that rate. Lines this rule explains feed nothing. Without that signal the same search
takes payers who withhold nothing (measured in holdout: 19 lines right and 10 wrong). The search stops at the largest
size that keeps MAX_CHANCE, so a set of many only counts where the cents say so. Two sets tie: neither.

A citation stays in the set: the text named part of what it paid and the rest is what the tax explains.

Known limit: it runs after the walk by date, so it frees no later receipt that depended on those balances."""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from math import comb

import polars as pl

from ..load import Phase
from ..model import Row
from ..policy import CREDIT_NOTES, WITHHOLDING_COUNTRIES, WITHHOLDING_RATES, Evidence
from ..state import OpenBalances
from .party_amount import MAX_CHANCE, OWN_SHORTFALL, ROUNDING_CENTS, PartyAmount
from .split_invoice import _COLUMNS

RULE = "PARTY-WITHHELD-SET"
CITED_RULE = "REF-WITHHELD-SET"
_FALLBACK = "FALLBACK-UNIDENTIFIED"
_CITED = "REF-TEXT"
_EXCEPTION = "SHORT_WITHHOLDING"
_SEARCHES = len(WITHHOLDING_RATES) * len(ROUNDING_CENTS)


def _largest_size(values: list[int]) -> int:
    """How many items a set can have before the sets searched could add up to any cash by chance."""
    total, size, sets = max(sum(abs(v) for v in values), 1), 0, 1
    while size < len(values) and (sets + comb(len(values), size + 1)) * _SEARCHES / total <= MAX_CHANCE:
        size += 1
        sets += comb(len(values), size)
    return size


def _sets(free: list, cash: int, named: set[str], rates: set[float], engine: PartyAmount) -> dict[frozenset, float]:
    """The sets of open documents, with the ones the text names, whose invoices net of one of the rates are the cash."""
    invoices = [(i[0], o) for i, o in free if i[0][:3] not in CREDIT_NOTES and o == i[4]
                and not OWN_SHORTFALL & engine.clauses.get(i[0], {}).keys()]
    notes = [(i[0], -o) for i, o in free if i[0][:3] in CREDIT_NOTES]
    credit = -sum(v for _, v in notes)
    found: dict[frozenset, float] = {}
    for rate in rates:
        net = [(i, o - round(o * rate)) for i, o in invoices]
        signed = [x for x in net if x[1] <= cash + credit + 1] + notes
        must = [x for x in signed if x[0] in named]
        if len(must) != len(named):
            continue
        rest = [x for x in signed if x[0] not in named]
        base = sum(v for _, v in must)
        for size in range(0 if named else 1, _largest_size([v for _, v in rest]) + 1):
            for chosen in combinations(rest, size):
                if abs(base + sum(v for _, v in chosen) - cash) <= 1:
                    found.setdefault(frozenset((*named, *(i for i, _ in chosen))), rate)
    return {key: rate for key, rate in found.items() if any(i[:3] not in CREDIT_NOTES for i in key)}


def _rate_of(rows: list[Row], cash: int) -> float | None:
    """The rate that explains this line: every invoice cleared with the exception, their net less notes the cash."""
    invoices = [r.amount_cents for r in rows if r.item_id[:3] not in CREDIT_NOTES]
    if any(r.exception != _EXCEPTION for r in rows if r.item_id[:3] not in CREDIT_NOTES):
        return None
    notes = sum(r.amount_cents for r in rows if r.item_id[:3] in CREDIT_NOTES)
    for rate in WITHHOLDING_RATES:
        if abs(sum(a - round(a * rate) for a in invoices) - notes - cash) <= len(invoices):
            return rate
    return None


def _witnesses(phase: Phase, rows: list[Row], engine: PartyAmount) -> dict[str, list[tuple[str, float, str]]]:
    """customer -> (date, rate, line) of what the rate explains exactly, before this stage touches anything."""
    lines = {r.bank_txn_id for r in rows if r.exception == _EXCEPTION}
    by_line: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        if row.bank_txn_id in lines and row.item_id:
            by_line[row.bank_txn_id].append(row)
    seen: dict[str, list[tuple[str, float, str]]] = defaultdict(list)
    for txn in phase.txns.filter(pl.col("bank_txn_id").is_in(list(lines))).select(_COLUMNS).iter_rows(named=True):
        cash, _ = engine._cash(txn)
        here = by_line[txn["bank_txn_id"]]
        rate = _rate_of(here, cash)
        if rate is not None and len({r.party_id for r in here}) == 1:
            seen[here[0].party_id].append((txn["booking_date"], rate, txn["bank_txn_id"]))
    return seen


def _earlier(seen: list[tuple[str, float, str]], date: str) -> dict[float, str]:
    """rate -> the first line that showed it, only among those before this date."""
    rates: dict[float, str] = {}
    for when, rate, line in sorted(seen):
        if when < date:
            rates.setdefault(rate, line)
    return rates


def _candidates(txn: dict, cash: int, currency: str, here: list[Row], seen: dict, balances: OpenBalances,
                engine: PartyAmount) -> dict:
    """party, rate and witness of each set that explains this line."""
    date = txn["booking_date"]
    named = {r.item_id for r in here}
    took = {r.item_id: r.amount_cents for r in here}
    found = {}
    for party in engine.parties.find(txn, "customer"):
        rates = _earlier(seen.get(party, ()), date)
        if engine.countries.get(party) not in WITHHOLDING_COUNTRIES or not rates:
            continue
        mine = [i for i in engine.items.get(party, ()) if i[2] <= date and i[3] == currency]
        if named - {i[0] for i in mine}:
            continue
        free = [(i, balances.open(i[0]) + took.get(i[0], 0)) for i in mine]
        free = [(i, o) for i, o in free if i[0] in named or engine.is_free(i, o, balances)]
        for key, rate in _sets(free, cash, named, set(rates), engine).items():
            found.setdefault(key, (party, rate, rates[rate]))
    return found


def _settle(txn: dict, key: frozenset, party: str, rate: float, witness: str, here: list[Row], currency: str,
            balances: OpenBalances, engine: PartyAmount) -> list[Row]:
    txn_id, date = txn["bank_txn_id"], txn["booking_date"]
    took = {r.item_id: r.amount_cents for r in here}
    rule = CITED_RULE if took else RULE
    why = (f"{Evidence.SEEN_RATE.name}: the only set net of {rate:.2%} among the open documents of {party}; "
           f"seen withholding at this rate in {witness}")
    out = []
    for item in sorted(key):
        exception = "" if item[:3] in CREDIT_NOTES else _EXCEPTION
        if item in took:
            amount = balances.open(item) + took[item]
            balances.restate(item, txn_id, amount, exception)
        else:
            amount = balances.open(item)
            balances.apply(item, amount, exception, txn_id, date)
            balances.history(item).sort(key=lambda h: h["bookingDate"])
        out.append(Row(txn_id, item, amount, currency, None, exception or None, rule, 0.85, party, None,
                       [{"kind": "customer", "ref": party}, {"kind": "bankLine", "ref": witness,
                                                             "label": "seen withholding at this rate"}],
                       [{"itemId": item, "amountCents": amount, "currency": currency, "why": why}]))
    engine.abstentions.pop(txn_id, None)
    return out


def apply(phase: Phase, rows: list[Row], balances: OpenBalances, engine: PartyAmount) -> None:
    """Rewrites the rows of each line. Call it before `engine.release()`."""
    seen = _witnesses(phase, rows, engine)
    if not seen:
        return
    by_txn: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        if row.rule in (_FALLBACK, _CITED):
            by_txn[row.bank_txn_id].append(row)
    settled = []
    lines = phase.txns.filter(pl.col("bank_txn_id").is_in(list(by_txn)) & (pl.col("amount_cents") > 0))
    for txn in lines.select(_COLUMNS).iter_rows(named=True):
        here = [r for r in by_txn[txn["bank_txn_id"]] if r.item_id]
        cash, currency = engine._cash(txn)
        if currency != txn["currency"] or any(r.exception == "DUPLICATE_PAYMENT" for r in here):
            continue
        found = _candidates(txn, cash, currency, here, seen, balances, engine)
        if len(found) != 1:
            continue
        (key, (party, rate, witness)), = found.items()
        if {r.item_id for r in here} == set(key) and all(
                r.exception == _EXCEPTION for r in here if r.item_id[:3] not in CREDIT_NOTES):
            continue
        settled.append((txn, key, party, rate, witness, here, currency))
    uses = Counter(item for _, key, *_ in settled for item in key)
    replaced = {entry[0]["bank_txn_id"]: _settle(*entry, balances, engine) for entry in settled
                if all(uses[item] == 1 for item in entry[1])}
    if replaced:
        rows[:] = [row for row in rows if row.bank_txn_id not in replaced] + [
            row for new in replaced.values() for row in new]

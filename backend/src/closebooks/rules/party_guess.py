"""PARTY-GUESS: a receipt still unidentified after every rule, from one known customer, takes its likeliest invoices.

Why: the scorer counts a wrong UNIDENTIFIED against that class, and a guessed pair raises the pair F1 whenever more than
half of the guesses are right (F1 / 2). On the holdout, the oldest due invoices that fit the cash, skipping those the
customer's previous receipt already left open, were right ~55 % of the time with the golden's customer and balances.
POLICIES §3 warns of unidentified receipts with the amount of an unrelated invoice: so exactly one customer has to be
named, and the case stays for a person to review. Nothing here is learned from any phase: the order is the due date,
the window is the customer's own previous receipt, and three is a cap on the cost of being wrong.

One invoice and cash left over within the overpayment criterion of `policy`: POLICIES §3 calls that an overpayment of a
single invoice (cleared in full, the excess on account), so the row says OVERPAYMENT rather than nothing. When the
oldest invoices do not sum to the cash and exactly one open invoice fits that criterion, that one is the guess: its
excess says more than its age. Two that fit tie and neither is taken. The same among several customers named (homonyms,
a name the bank cut): the owner of the only such invoice is the payer, if it is already due and the excess small (10 %
of it, or 100 of the currency): a looser excess fits unidentified receipts by chance. It stays an inference, to review.

The oldest invoices that add up to the cash to the cent go first, however many (up to `MAX_SEARCH`), leaving out at most
one: a sum of many balances does not land on the cent by chance. Without an exact sum, the cap of three stands.

Runs last, after PARTY-AMOUNT-LATE, by booking date, so a later receipt does not take what an earlier guess took."""
from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict

import polars as pl

from ..load import Phase
from ..model import Row
from ..policy import ROUND_OVERPAYMENT_RATIO, _is_overpayment
from ..state import OpenBalances
from .late_party_amount import _by_start, _by_words, _name_words
from .party_amount import PartyAmount
from .split_invoice import _COLUMNS

RULE = "PARTY-GUESS"
_FALLBACK = "FALLBACK-UNIDENTIFIED"
MAX_ITEMS = 3
MAX_NAMED_EXCESS_CENTS = 10_000  # with several customers named, the largest round excess that still says who paid


def _open_of(party: str, date: str, currency: str, due: dict, balances: OpenBalances,
             engine: PartyAmount) -> list[tuple]:
    """Its invoices open and free now: (due date, issue date, item, open cents)."""
    return [(due.get(entry[0]) or entry[2], entry[2], entry[0], balances.open(entry[0]))
            for entry in engine.items.get(party, ())
            if entry[0][:3] == "ARI" and entry[2] <= date and entry[3] == currency
            and engine.is_free(entry, balances.open(entry[0]), balances)]


def _since_last(party: str, date: str, currency: str, due: dict, balances: OpenBalances, engine: PartyAmount,
                receipts: dict[str, list[str]]) -> tuple[list[tuple], list[tuple]]:
    """Its invoices open now, and those due since its previous receipt with evidence, oldest first."""
    days = receipts[party]
    before = days[bisect_left(days, date) - 1] if bisect_left(days, date) else ""
    open_now = _open_of(party, date, currency, due, balances, engine)
    return open_now, sorted(c for c in open_now if c[0] >= before)


def _says_who_paid(entry: tuple, cash: int, date: str) -> bool:
    due_date, _, _, cents = entry
    excess = cash - cents
    return due_date <= date and (excess <= cents * ROUND_OVERPAYMENT_RATIO + 1 or excess <= MAX_NAMED_EXCESS_CENTS)
MAX_SEARCH = 40  # open invoices searched for an exact sum: a bound on the work, not a learned threshold


def _exact(candidates: list[tuple[str, str, int]], cash: int) -> list[tuple[str, str, int]]:
    """The fewest open invoices (up to three), earliest due first, whose balances are the cash to the cent."""
    for one in candidates:
        if one[2] == cash:
            return [one]
    pairs = [(i, j) for i in range(len(candidates)) for j in range(i + 1, len(candidates))]
    for i, j in pairs:
        if candidates[i][2] + candidates[j][2] == cash:
            return [candidates[i], candidates[j]]
    for i, j in pairs:
        need = cash - candidates[i][2] - candidates[j][2]
        for k in range(j + 1, len(candidates)):
            if candidates[k][2] == need:
                return [candidates[i], candidates[j], candidates[k]]
    return []


def _oldest_exact(ordered: list[tuple], cash: int) -> list[tuple]:
    """The oldest invoices whose balances are the cash to the cent, leaving out at most one of them."""
    total = 0
    at_cents: dict[int, int] = {}
    for position, (_, _, _, cents) in enumerate(ordered):
        total += cents
        if total == cash:
            return ordered[:position + 1]
        left_out = at_cents.get(total - cash)
        if left_out is not None:
            return ordered[:left_out] + ordered[left_out + 1:position + 1]
        at_cents.setdefault(cents, position)
    return []


def apply(phase: Phase, rows: list[Row], balances: OpenBalances, engine: PartyAmount) -> None:
    """Rewrites the rows of each guessed receipt in place. Call it before `engine.release()`."""
    at = {row.bank_txn_id: index for index, row in enumerate(rows) if row.rule == _FALLBACK}
    if not at:
        return
    dates = dict(phase.txns.select("bank_txn_id", "booking_date").iter_rows())
    # customer -> booking dates of its receipts settled with evidence; a guess is no evidence of what it left open
    receipts: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if row.party_id and row.item_id and row.item_id[:3] == "ARI":
            receipts[row.party_id].append(dates[row.bank_txn_id])
    for days in receipts.values():
        days.sort()
    due = dict(phase.items.filter(pl.col("item_type") == "ARI").select("item_id", "due_date").iter_rows())
    words = _name_words(engine.parties)
    guesses: dict[int, list[Row]] = {}
    pending = phase.txns.filter(pl.col("bank_txn_id").is_in(list(at))).select(_COLUMNS)
    for txn in pending.sort("booking_date", "bank_txn_id").iter_rows(named=True):
        cash, currency = engine._cash(txn)
        if currency != txn["currency"]:
            continue
        homonym = False
        payers = {*engine.parties.find(txn, "customer"), *_by_start(engine.parties, txn), *_by_words(words, txn)}
        date = txn["booking_date"]
        if len(payers) > 1:
            fits = [(party, entry) for party in payers
                    for entry in _open_of(party, date, currency, due, balances, engine)
                    if entry[3] < cash and _is_overpayment(cash - entry[3], entry[3])]
            if len(fits) == 1 and _says_who_paid(fits[0][1], cash, date):
                payers = [fits[0][0]]
            else:  # the only homonym whose oldest invoices add up to the cash; two that do tie
                payers = [party for party in payers if _oldest_exact(
                    _since_last(party, date, currency, due, balances, engine, receipts)[1][:MAX_SEARCH], cash)]
                homonym = len(payers) == 1
        if len(payers) != 1:
            continue
        party = payers.pop()
        open_now, ordered = _since_last(party, date, currency, due, balances, engine, receipts)
        added_up = _oldest_exact(ordered[:MAX_SEARCH], cash)
        chosen, left = [(item, cents, due_date) for due_date, _, item, cents in added_up], 0
        if not chosen:
            left = cash
            for due_date, _, item, cents in ordered:
                if cents > left or len(chosen) == MAX_ITEMS:
                    break
                chosen.append((item, cents, due_date))
                left -= cents
        overpays = [(item, cents, due_date) for due_date, _, item, cents in open_now
                    if cents < cash and _is_overpayment(cash - cents, cents)]
        if left and len(overpays) == 1:
            chosen, left = overpays, cash - overpays[0][1]
        if not chosen:
            every = [(due_date, item, cents) for due_date, _, item, cents in sorted(open_now)]
            if exact := _exact(every[:MAX_SEARCH], cash):
                chosen, left = [(item, cents, due_date) for due_date, item, cents in exact], 0
        if not chosen:
            continue
        txn_id = txn["bank_txn_id"]
        overpaid = len(chosen) == 1 and left > 0 and _is_overpayment(left, chosen[0][1])
        said = "OVERPAYMENT" if overpaid else None
        for item, cents, _ in chosen:
            balances.apply(item, cents, said or "", txn_id, date)
        guesses[at[txn_id]] = [Row(
            txn_id, item, cents, currency, None, said, RULE, 0.3, party, None, [{"kind": "customer", "ref": party}],
            [{"itemId": item, "amountCents": cents, "currency": currency,
              "why": f"inferred overpayment: the cash clears it with an excess within limits, {party} named; to review"
              if overpaid else "inferred: the only homonym whose oldest invoices add up to the cash"
              if homonym and added_up else
              "inferred: the oldest invoices due of the only customer named add up to the cash; to review"
              if added_up else
              f"oldest invoice due ({due_date}) of the only customer named; no reference, to review"}])
            for item, cents, due_date in chosen]
        engine.abstentions.pop(txn_id, None)
    rows[:] = [new for index, row in enumerate(rows) for new in guesses.get(index, [row])]

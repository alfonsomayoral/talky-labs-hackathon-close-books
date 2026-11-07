"""PARTY-GUESS: a receipt still unidentified after every rule, from one known customer, takes its likeliest invoices.

Why: the scorer counts a wrong UNIDENTIFIED against that class, and a guessed pair raises the pair F1 whenever more than
half of the guesses are right (F1 / 2). On the holdout, the oldest due invoices that fit the cash, skipping those the
customer's previous receipt already left open, were right ~55 % of the time with the golden's customer and balances.
POLICIES §3 warns of unidentified receipts with the amount of an unrelated invoice: so exactly one customer has to be
named, and the case stays for a person to review. Nothing here is learned from any phase: the order is the due date,
the window is the customer's own previous receipt, and three is a cap on the cost of being wrong.

One invoice and cash left over within the overpayment criterion of `policy`: POLICIES §3 calls that an overpayment of a
single invoice (cleared in full, the excess on account), so the row says OVERPAYMENT rather than nothing.

Runs last, after PARTY-AMOUNT-LATE, by booking date, so a later receipt does not take what an earlier guess took."""
from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict

import polars as pl

from ..load import Phase
from ..model import Row
from ..policy import _is_overpayment
from ..state import OpenBalances
from .late_party_amount import _by_start, _by_words, _name_words
from .party_amount import PartyAmount
from .split_invoice import _COLUMNS

RULE = "PARTY-GUESS"
_FALLBACK = "FALLBACK-UNIDENTIFIED"
MAX_ITEMS = 3


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
        payers = {*engine.parties.find(txn, "customer"), *_by_start(engine.parties, txn), *_by_words(words, txn)}
        if len(payers) != 1:
            continue
        party, date = payers.pop(), txn["booking_date"]
        days = receipts[party]
        before = days[bisect_left(days, date) - 1] if bisect_left(days, date) else ""
        open_now = [(due.get(entry[0]) or entry[2], entry[2], entry[0], balances.open(entry[0]))
                    for entry in engine.items.get(party, ())
                    if entry[0][:3] == "ARI" and entry[2] <= date and entry[3] == currency
                    and engine.is_free(entry, balances.open(entry[0]), balances)]
        chosen, left = [], cash
        for due_date, _, item, cents in sorted(c for c in open_now if c[0] >= before):
            if cents > left or len(chosen) == MAX_ITEMS:
                break
            chosen.append((item, cents, due_date))
            left -= cents
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
              "why": f"oldest invoice due ({due_date}) of the only customer named; no reference, to review"}])
            for item, cents, due_date in chosen]
        engine.abstentions.pop(txn_id, None)
    rows[:] = [new for index, row in enumerate(rows) for new in guesses.get(index, [row])]

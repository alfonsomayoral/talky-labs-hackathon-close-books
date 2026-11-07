"""PARTY-AMOUNT-LATE: the payer the bank text names and the exact cash point to one open invoice.

Why it generalizes: the evidence is the payer named on the bank line and an exact balance, with nothing learned from any
phase. The official examples of the challenge say so for a noisy reference ("el ordenante y el importe exacto
identifican la única partida abierta que encaja"; hackathon.usetalky.com/ejemplos). POLICIES §5.5 says references may be
missing ("name or IBAN only") and that the name in the text is often cut or a trade name; hence the candidates by the
start of the name and by its words. POLICIES §3 warns that some unidentified receipts have exactly the amount of an
unrelated open invoice. So the payer is required, the invoice has to be the only one among all the candidates, and the
case stays for a person to review.

A later payment already left that invoice partial: by date this receipt is the partial one and the later one closes it.

PARTY-DUPLICATE-LATE: nothing open for that cash, and exactly one invoice of the payer named, of that total, settled by
one receipt of exactly that amount in the last month: POLICIES §3 calls a second payment a duplicate. It is an
inference, not evidence: a fixed instalment whose invoice is missing looks the same, so no other invoice of that total
in the previous year, no citation of another document, a low confidence and the case stays for review.

Known limit: it runs after the walk by date, so it frees no later receipt that depended on that balance."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date, timedelta

import polars as pl

from ..load import Phase
from ..model import Row
from ..state import OpenBalances
from .parties import LEGAL_FORMS, PREFIX_CHARS, PartyIndex, _common_prefix, _word_starts, normalize
from .party_amount import PartyAmount, _alnum
from .split_invoice import _COLUMNS

RULE = "PARTY-AMOUNT-LATE"
_FALLBACK = "FALLBACK-UNIDENTIFIED"
MIN_NAME_WORDS = 2  # one word of a name is in too many bank texts to say who paid
RULE_AGAIN = "PARTY-DUPLICATE-LATE"
PAID_AGAIN_DAYS = 30  # a month: past it, the same amount is more likely another invoice than the same one again
INSTALMENT_DAYS = 365  # a year: another invoice of that total in it says the amount recurs


def _longest(best: dict[str, int]) -> set[str]:
    return {party for party, length in best.items() if length == max(best.values())}


def _by_start(parties: PartyIndex, txn: dict) -> set[str]:
    """Customers whose name starts at a word of the text, as cut as the bank left it: the longest match."""
    raw = txn["text"] or ""
    best: dict[str, int] = {}
    for text in {normalize(raw.replace(" | ", "")), normalize(raw)}:
        for position in _word_starts(text):
            start = text[position:position + PREFIX_CHARS]
            for norm, party in parties.by_prefix.get(("customer", txn["entity"], start), ()):
                best[party] = max(best.get(party, 0), _common_prefix(norm, text, position))
    return _longest(best)


def _name_words(parties: PartyIndex) -> dict[tuple[str, str], list[tuple[str, frozenset[str]]]]:
    """(entity, word) -> the customers with that word in a name of at least two words, legal form aside."""
    index: dict[tuple[str, str], list[tuple[str, frozenset[str]]]] = defaultdict(list)
    for (kind, entity, norm), found in parties.by_name.items():
        words = frozenset(word for word in norm.split() if word not in LEGAL_FORMS)
        if kind == "customer" and len(words) >= MIN_NAME_WORDS:
            for word in words:
                index[entity, word] += [(party, words) for party in found]
    return index


def _by_words(index: dict, txn: dict) -> set[str]:
    """Customers with every word of their name in the text, in any order: the longest name."""
    in_text = set(normalize(txn["text"]).split())
    best: dict[str, int] = {}
    for word in in_text:
        for party, words in index.get((txn["entity"], word), ()):
            if words <= in_text:
                best[party] = max(best.get(party, 0), len(words))
    return _longest(best)


def _open_invoices(balances: OpenBalances, engine: PartyAmount) -> dict[tuple, list[tuple]]:
    found: dict[tuple, list[tuple]] = defaultdict(list)
    for party, entries in engine.items.items():
        for entry in entries:
            if entry[0][:3] == "ARI" and balances.open(entry[0]) > 0:  # most are closed: not worth indexing
                found[party, entry[3], balances.open(entry[0])].append((party, entry))
    return found


def _settled_once_lately(entry: tuple, balances: OpenBalances, booking_date: str, lines: Counter) -> bool:
    """Closed by one line of this run, that receipt paying this invoice alone and in full, in the last month."""
    history = balances.history(entry[0])
    if balances.open(entry[0]) > 0 or len(history) != 1:
        return False
    first = history[0]
    days = (date.fromisoformat(booking_date) - date.fromisoformat(first["bookingDate"])).days
    return first["amountCents"] == entry[4] and lines[first["bankTxnId"]] <= 1 and 0 <= days <= PAID_AGAIN_DAYS


def _looks_recurring(entry: tuple, entries: list[tuple], booking_date: str) -> bool:
    since = (date.fromisoformat(booking_date) - timedelta(days=INSTALMENT_DAYS)).isoformat()
    return any(other[0] != entry[0] and other[0][:3] == "ARI" and other[4] == entry[4] and since <= other[2]
               for other in entries)


def _cites_another(entry: tuple, txn: dict, engine: PartyAmount) -> bool:
    return any(hit[0] != entry[0] for token in engine._tokens(txn)
               for hit in engine.by_number.get((txn["entity"], _alnum(token)), ()))


def _paid_again(paid: list[tuple], rows: list[Row], at: dict, balances: OpenBalances, engine: PartyAmount) -> None:
    uses = Counter(entry[0] for *_, entry in paid)
    for txn, cash, currency, party, entry in paid:
        if uses[entry[0]] > 1:
            continue
        item, txn_id = entry[0], txn["bank_txn_id"]
        balances.apply(item, cash, "DUPLICATE_PAYMENT", txn_id, txn["booking_date"])
        rows[at[txn_id]] = Row(
            txn_id, item, cash, currency, None, "DUPLICATE_PAYMENT", RULE_AGAIN, 0.3, party, None,
            [{"kind": "customer", "ref": party}],
            [{"itemId": item, "amountCents": cash, "currency": currency,
              "why": "inference: the payer named paid this total of an invoice settled days ago; to review"}])
        engine.abstentions.pop(txn_id, None)


def apply(phase: Phase, rows: list[Row], balances: OpenBalances, engine: PartyAmount) -> None:
    """Rewrites the row of each receipt in place. Call it before `engine.release()`."""
    at = {row.bank_txn_id: index for index, row in enumerate(rows) if row.rule == _FALLBACK}
    invoices = _open_invoices(balances, engine)
    words = _name_words(engine.parties)
    lines = Counter(row.bank_txn_id for row in rows)
    settled, paid = [], []
    for txn in phase.txns.filter(pl.col("bank_txn_id").is_in(list(at))).select(_COLUMNS).iter_rows(named=True):
        cash, currency = engine._cash(txn)
        if currency != txn["currency"]:
            continue
        candidates = sorted({*engine.parties.find(txn, "customer"), *_by_start(engine.parties, txn),
                             *_by_words(words, txn)})
        found = [(party, entry) for party in candidates for party, entry in invoices.get((party, currency, cash), ())
                 if entry[2] <= txn["booking_date"]]
        if len(found) == 1:
            settled.append((txn, cash, currency, candidates, *found[0]))
        elif not found:
            closed = [(party, entry) for party in candidates for entry in engine.items.get(party, ())
                      if entry[0][:3] == "ARI" and entry[3] == currency and entry[4] == cash
                      and _settled_once_lately(entry, balances, txn["booking_date"], lines)]
            if (len(closed) == 1 and not _cites_another(closed[0][1], txn, engine)
                    and not _looks_recurring(closed[0][1], engine.items[closed[0][0]], txn["booking_date"])):
                paid.append((txn, cash, currency, *closed[0]))
    uses = Counter(entry[0] for *_, entry in settled)
    for txn, cash, currency, candidates, party, entry in settled:
        if uses[entry[0]] > 1:
            continue
        item, txn_id = entry[0], txn["bank_txn_id"]
        history = balances.history(item)
        last = max(history, key=lambda h: h["bookingDate"], default=None)
        earlier = last is not None and last["bookingDate"] > txn["booking_date"]
        if earlier and last["exception"] != "PARTIAL":
            continue
        exception = "PARTIAL" if earlier else None
        balances.apply(item, cash, exception or "", txn_id, txn["booking_date"])
        balances.history(item).sort(key=lambda h: h["bookingDate"])
        if earlier:  # the walk took the later receipt for the partial: by date this one is, and the later closes it
            last["exception"] = ""
            for index, row in enumerate(rows):
                if row.bank_txn_id == last["bankTxnId"] and row.item_id == item:
                    rows[index] = replace(row, exception=None)
        rows[at[txn_id]] = Row(
            txn_id, item, cash, currency, None, exception, RULE, 0.85, party, None,
            [{"kind": "customer", "ref": party}],
            [{"itemId": item, "amountCents": cash, "currency": currency,
              "why": f"only open invoice with this balance among {', '.join(candidates)}"}])
        engine.abstentions.pop(txn_id, None)
    _paid_again(paid, rows, at, balances, engine)

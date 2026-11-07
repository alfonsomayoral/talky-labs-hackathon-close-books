"""PARTY-AMOUNT-LATE: the payer the bank text names and the exact cash point to one open invoice.

Why it generalizes: the evidence is the payer named on the bank line and an exact balance, with nothing learned from any
phase. The official examples of the challenge say so for a noisy reference ("el ordenante y el importe exacto
identifican la única partida abierta que encaja"; hackathon.usetalky.com/ejemplos). POLICIES §5.5 says references may be
missing ("name or IBAN only") and that the name in the text is often cut or a trade name; hence the candidates by the
start of the name and by its words. POLICIES §3 warns that some unidentified receipts have exactly the amount of an
unrelated open invoice. So the payer is required, the invoice has to be the only one among all the candidates, and the
case stays for a person to review.

A later payment already left that invoice partial: by date this receipt is the partial one and the later one closes it.

Known limit: it runs after the walk by date, so it frees no later receipt that depended on that balance."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace

import polars as pl

from ..load import Phase
from ..model import Row
from ..state import OpenBalances
from .parties import LEGAL_FORMS, PREFIX_CHARS, PartyIndex, _common_prefix, _word_starts, normalize
from .party_amount import PartyAmount
from .split_invoice import _COLUMNS

RULE = "PARTY-AMOUNT-LATE"
_FALLBACK = "FALLBACK-UNIDENTIFIED"
MIN_NAME_WORDS = 2  # one word of a name is in too many bank texts to say who paid


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


def apply(phase: Phase, rows: list[Row], balances: OpenBalances, engine: PartyAmount) -> None:
    """Rewrites the row of each receipt in place. Call it before `engine.release()`."""
    at = {row.bank_txn_id: index for index, row in enumerate(rows) if row.rule == _FALLBACK}
    invoices = _open_invoices(balances, engine)
    words = _name_words(engine.parties)
    settled = []
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

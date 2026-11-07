"""R3 and R4, evaluated by booking date: the party, its items open at that moment and the numbers the text cites."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date as Date
from datetime import timedelta
from fractions import Fraction
from itertools import combinations
from math import floor

import polars as pl

from ..documents.pdfs import phase_clauses
from ..load import cancelled_item_ids
from ..model import Proposal
from ..policy import (
    FEE_LIMIT_EUR_CENTS,
    FEE_LIMIT_RATIO,
    MAX_CHANCE,
    ROUND_FRACTIONS,
    SEPA_COUNTRIES,
    SHARE_WINDOW,
    WITHHOLDING_COUNTRIES,
    WITHHOLDING_RATES,
    Terms,
    _in_terms,
    cross_border,
    fee_fits,
    fee_stated,
)
from ..state import OpenBalances
from .agency import paid_by_agency, tail_key
from .parties import PartyIndex, normalize

_TOKEN = re.compile(r"[A-Z0-9][A-Z0-9/\-]{2,}")
MIN_SUFFIX = 3
STRONG_SUFFIX = 5
MIN_CUT = 6
LONG_CUT = 8
MAX_SUBSET_ITEMS = 24
MAX_FULL_SEARCH = 22  # a bound on the search per line; what a unique subset means is `_chance`
ALWAYS_SEARCHED = 16  # up to here a unique subset has always been taken, whatever its chance
MAX_SKIPPED = 2  # invoices a customer leaves out of the run it pays
# A receipt with no reference does not pay an invoice not yet due; the week is for weekends and value dates. Measured
# on holdout, unique sets and errors: 1,548 and 7 at +7 days, 1,528 and 2 at +10.
DUE_TOLERANCE_DAYS = 7
MAX_DUE_SEARCH_BYTES = 200_000_000  # the search holds one big integer per item, of as many bits as cents in the cash
NUMBER_ALONE_TOLERANCE = 0.05
MONTHS = {name: number for number, names in enumerate((
    "ENERO JANUARY JANVIER JANUAR GENNAIO JANEIRO ENE JAN", "FEBRERO FEBRUARY FEVRIER FEBRUAR FEBBRAIO FEVEREIRO FEB",
    "MARZO MARCH MARS MARZ MARCO MAR", "ABRIL APRIL AVRIL APRILE ABR APR", "MAYO MAY MAI MAGGIO MAIO",
    "JUNIO JUNE JUIN JUNI GIUGNO JUNHO JUN", "JULIO JULY JUILLET JULI LUGLIO JULHO JUL",
    "AGOSTO AUGUST AOUT AGO AUG", "SEPTIEMBRE SEPTEMBER SEPTEMBRE SETTEMBRE SETEMBRO SEP SEPT SET",
    "OCTUBRE OCTOBER OCTOBRE OKTOBER OTTOBRE OUTUBRO OCT OKT OTT OUT",
    "NOVIEMBRE NOVEMBER NOVEMBRE NOVEMBRO NOV", "DICIEMBRE DECEMBER DECEMBRE DEZEMBER DICEMBRE DEZEMBRO DIC DEC DEZ",
), 1) for name in names.split()}
_MONTH = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b(?: (\d{2}|\d{4})\b)?")
MAX_TIED_SUBSETS = 5
CREDIT_NOTES = ("ARC", "APC")
_WITHHOLDING = (0.0125, 0.015, 0.10)
ROUNDING_CENTS = (0, -1, 1)  # each invoice rounds its tax apart: the sum may miss the cash by a cent
OWN_SHORTFALL = frozenset(("retention", "advance_deduction", "instalments"))  # the PDF says why less is paid


def _alnum(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _discount_pct(phase) -> dict[str, float]:
    if "payment_terms" not in phase.masters or "payment_terms" not in phase.items.columns:
        return {}
    rows = phase.masters["payment_terms"].iter_rows(named=True)
    pct = {r["code"]: float(r["early_payment_discount_pct"]) for r in rows if r["early_payment_discount_pct"]}
    with_terms = phase.items.filter(pl.col("payment_terms").is_in(list(pct)))
    return {i: pct[c] for i, c in with_terms.select("item_id", "payment_terms").iter_rows()}


_MANY = object()


def _chance(sets: float, values: list[int]) -> float:
    """How many of the sets searched would add up to a given cash by chance: they spread over the cents of the sum."""
    return sets / max(sum(abs(v) for v in values), 1)


def _sums(pairs: list) -> dict:
    """Every subset sum of the pairs: its bitmask, or _MANY when two subsets reach it."""
    sums: dict = {0: 0}
    for bit, (_, value) in enumerate(pairs):
        for total, mask in list(sums.items()):
            reached = total + value
            sums[reached] = _MANY if reached in sums or mask is _MANY else mask | 1 << bit
    return sums


def _unique_subset(signed: list, cash: int, min_size: int) -> list[str] | None:
    half = len(signed) // 2
    left = _sums(signed[:half])
    found = None
    for total, mask in _sums(signed[half:]).items():
        match = left.get(cash - total)
        if match is None:
            continue
        if mask is _MANY or match is _MANY or found is not None:
            return None
        found = (match, mask)
    if found is None:
        return None
    chosen = [signed[i][0] for i in range(half) if found[0] >> i & 1]
    chosen += [signed[half + i][0] for i in range(len(signed) - half) if found[1] >> i & 1]
    return chosen if len(chosen) >= min_size else None


def _tied_subsets(signed: list, cash: int) -> list[list[str]]:
    ties = [[i for i, _ in combo] for size in (2, 3) for combo in combinations(signed, size)
            if sum(v for _, v in combo) == cash]
    return ties[:MAX_TIED_SUBSETS] if len(ties) > 1 else []


def _small_subset(signed: list, cash: int, min_size: int) -> list[str] | None:
    """Too many candidates for a whole search to be unique: only sets of up to four, the smallest size that fits."""
    if min_size == 1:
        hits = [i for i, v in signed if v == cash]
        if hits:
            return hits if len(hits) == 1 else None
    pairs: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for a in range(len(signed)):
        for b in range(a + 1, len(signed)):
            pairs[signed[a][1] + signed[b][1]].append((signed[a][0], signed[b][0]))
    found = {frozenset(p) for p in pairs.get(cash, ())}
    if not found:
        for item, value in signed:
            found |= {frozenset((item, *p)) for p in pairs.get(cash - value, ()) if item not in p}
    if not found:
        for total, group in pairs.items():
            for p in group:
                found |= {frozenset((*p, *q)) for q in pairs.get(cash - total, ()) if not set(p) & set(q)}
            if len(found) > 1:
                return None
    return sorted(found.pop()) if len(found) == 1 else None


def _discount_days(phase) -> dict[str, int]:
    if "payment_terms" not in phase.masters or "payment_terms" not in phase.items.columns:
        return {}
    rows = phase.masters["payment_terms"].iter_rows(named=True)
    days = {r["code"]: int(r["discount_days"]) for r in rows if r["early_payment_discount_pct"]}
    with_terms = phase.items.filter(pl.col("payment_terms").is_in(list(days)))
    return {i: days[c] for i, c in with_terms.select("item_id", "payment_terms").iter_rows()}


def _sets_up_to_two(values: list[int], target: int) -> list[list[int]]:
    """Up to two sets of positions adding up to the target. reach[k] has bit s set if the items from k on can sum s,
    so the walk only follows branches with a solution and stops at the second one."""
    mask = (1 << (target + 1)) - 1
    reach = [1] * (len(values) + 1)
    for k in range(len(values) - 1, -1, -1):
        reach[k] = (reach[k + 1] | (reach[k + 1] << values[k])) & mask
    if not reach[0] >> target & 1:
        return []
    found: list[list[int]] = []
    pending = [(0, target, ())]
    while pending and len(found) < 2:
        k, left, chosen = pending.pop()
        if k == len(values):
            found.append(list(chosen))
            continue
        if reach[k + 1] >> left & 1:
            pending.append((k + 1, left, chosen))
        if values[k] <= left and reach[k + 1] >> (left - values[k]) & 1:
            pending.append((k + 1, left - values[k], (*chosen, k)))
    return found


def _net(pairs: list) -> int:
    return sum(-o if i[0][:3] in CREDIT_NOTES else o for i, o in pairs)


def document_says(clauses: dict | None, total: int, cash: int) -> str | None:
    """The exception of a cash the invoice's own PDF foresees, or None. Why it generalizes: the official example of
    ar_retention pays the PDF's amount without citing the invoice and its row is PARTIAL, and POLICIES §3 lists the
    first payment of a guarantee retention and of an invoice net of an advance as PARTIAL, and the release as empty.

    The percentage gives the retained part, rounded half up, whatever the total: the PDF prints it cut, so what it says
    is payable can be a cent above the cash. The advance is an amount, so its net is the one printed."""
    clauses = clauses or {}
    if retention := clauses.get("retention"):
        retained = floor(Fraction(total) * Fraction(str(retention["pct"])) / 100 + Fraction(1, 2))
        if cash in (retained, total - retained):
            return "" if cash == retained else "PARTIAL"
    return "PARTIAL" if cash == clauses.get("advance_deduction", {}).get("netDueCents") else None


def _has_pdfs(phase) -> bool:
    return hasattr(phase, "dir") and (phase.dir / "pdfs" / "index.csv").exists()


def _clauses(phase) -> dict[str, dict[str, dict]]:
    """Facts of the invoice PDFs per item. Parsers extract them; only the rules below decide with them."""
    if not _has_pdfs(phase):
        return {}
    facts = phase_clauses(phase)
    return {item: {**{c.kind: c.value for c in doc.clauses}, "_pdf": {"path": doc.path}}
            for item, doc in facts._by_item.items() if doc.clauses}


def _month_of(text: str, party_words: set[str]) -> tuple[int, int | None] | None:
    """A month word of the party's own name is the name, unless a year follows it."""
    for match in _MONTH.finditer(text):
        year = match[2]
        if year or match[1] not in party_words:
            return MONTHS[match[1]], (2000 + int(year) % 100) if year else None
    return None


def _as_taught(proposal: Proposal, rule: dict) -> Proposal:
    proposal.rule, proposal.confidence = "MEMORY-RULE", 1.0
    proposal.sources = [{"kind": "memoryRule", "ref": rule["ruleId"]}]
    return proposal


def _left_out(values: list[int], start: int, end: int, excess: int, skipped: int, must: list[int]) -> list[tuple]:
    """Invoices strictly inside the run whose amounts are the excess: the two ends stay, or it is a shorter run."""
    if excess == 0:
        return [()]
    if excess < 0 or not skipped:
        return []
    inside = [k for k in range(start + 1, end) if k not in must and values[k] <= excess]
    hits: list[tuple] = [(k,) for k in inside if values[k] == excess]
    if skipped > 1:
        at = defaultdict(list)
        for k in inside:
            at[values[k]].append(k)
        hits += [(k, other) for k in inside for other in at.get(excess - values[k], ()) if other > k]
    return hits


class PartyAmount:
    def __init__(self, phase, reserved: set[str]):
        self.reserved = reserved
        self.memory = None
        self.clauses = _clauses(phase)
        self.cancelled = cancelled_item_ids(phase.items) if "reason" in phase.items.columns else set()
        # bank_txn_id -> why the engine proposed nothing although it had evidence: nobody reads this to decide
        self.abstentions: dict[str, dict] = {}
        self._pending: list[tuple[str, list[str]]] = []
        items = phase.items
        # TRAIN has no opening balances: items issued before its first line are candidates only if something cites them.
        self.unknown_before = phase.start if getattr(phase, "name", "") == "train" else ""
        self.terms_pct = _discount_pct(phase)
        self.discount_days = _discount_days(phase)
        customers = phase.masters["customers"]
        self.countries = dict(customers.select("customer_id", "country").iter_rows()) if (
            "country" in customers.columns) else {}
        known = items.filter(pl.col("party_id").is_not_null())
        # A credit note names the invoice it credits (POLICIES §5.9): its printed number, as the citations compare it.
        self.credits = {} if "related_document" not in items.columns else {
            note: _alnum(number) for note, number in items.filter(pl.col("related_document").is_not_null()).select(
                "item_id", "related_document").iter_rows()}
        self.parties = PartyIndex(phase.masters, known.select("entity", "party_id", "party_name", "item_type").unique(),
                                  phase_clauses(phase).notices() if _has_pdfs(phase) else ())
        self.related = {} if "related_document" not in items.columns else {
            i: _alnum(r) for i, r in items.filter(pl.col("related_document").is_not_null())
            .select("item_id", "related_document").iter_rows() if i[:3] in CREDIT_NOTES}
        self._known = known
        self._due = dict(known.filter(pl.col("due_date").is_not_null()).select("item_id", "due_date").iter_rows())
        self.reindex()

    def release(self) -> None:
        """Before writing the run: the indexes are the biggest thing in memory and nothing needs them after resolve."""
        self.items, self.by_number, self.by_tail, self.clauses, self.related = {}, {}, {}, {}, {}
        self._due = {}
        self.parties = None
        self._known = None

    def reindex(self) -> None:
        self.items: dict[str, list[tuple]] = defaultdict(list)
        self.by_number: dict[tuple[str, str], list[tuple]] = defaultdict(list)
        self.by_tail: dict[tuple[str, str], list[tuple[str, tuple]]] = defaultdict(list)
        known = self._known
        replaced = {i: _alnum(c["replaces"]["replaces"]) for i, c in self.clauses.items() if "replaces" in c}
        columns = ("item_id", "party_id", "document_number", "issue_date", "currency", "total_cents", "customer_po",
                   "entity")
        for item_id, party, number, issued, currency, total, po, entity in known.select(columns).iter_rows():
            if item_id in self.cancelled:
                continue
            compact = _alnum(number or "")
            entry = (item_id, number or "", issued or "", currency, total, (po or "").upper(), compact,
                     re.sub(r"\D", "", number or ""), replaced.get(item_id, ""))
            self.items[party].append(entry)
            if len(compact) >= MIN_CUT:
                self.by_number[entity, compact].append(entry)
            if item_id[:3] == "ARI" and (tail := tail_key(entry[7])):
                self.by_tail[entity, tail].append((party, entry))

    def __call__(self, txn: dict, balances: OpenBalances) -> Proposal | None:
        kind = "customer" if txn["amount_cents"] > 0 else "supplier"
        cash, currency = self._cash(txn)
        self._pending = []
        if self.memory is not None:
            taught = self._taught(txn, kind, cash, currency, balances)
            if taught:
                return taught
        parties = self.parties.find(txn, kind)
        results = [r for party in parties if (r := self._or_netted(party, txn, cash, currency, balances))]
        for found in results:
            if notice := self.parties.notice_of(txn, found.party_id):
                found.sources.append({"kind": "pdf", "ref": notice})
        if len(results) == 1:
            return results[0]
        homonym = self._only_homonym_with_the_cash(results, cash, currency, balances)
        if homonym:
            return homonym
        found = self._by_number_alone(txn, cash, currency, balances)
        if found:
            return found
        group = self._in_the_group(parties, txn, cash, currency, balances) if not results else None
        if group:
            return group
        factory = None
        if not results and kind == "supplier":
            factory = self._for_another_entity(txn, cash, currency, balances)
        if factory:
            return factory
        if results:
            self._abstain(txn, "parties", [(r.party_id, [i for i, _ in r.lines]) for r in results], balances)
        elif self._pending:
            self._abstain(txn, "subsets", self._pending, balances)
        elif kind == "customer" and not parties:
            return paid_by_agency(self, txn, cash, currency, balances)
        else:
            return self._credit_payout(txn, cash, currency, balances)
        return None

    def _or_netted(self, party: str, txn: dict, cash: int, currency: str, balances) -> Proposal | None:
        """The match of the party; when it is only what the text cites and the cash does not explain, the cited
        invoices completed with other invoices that fell due, with credit notes or without (`_netted_cited`). The one
        place this block is called from.

        From PR 117 of lorenzo-redolfi, restricted to the cobros that cite an invoice. Why it generalizes: the text
        cites invoices of the batch (the bank cuts it, so not all) and the arithmetic closes the rest to the cent,
        with the credit notes the customer nets (POLICIES §5.9) or none, so the batch is read from the citation and
        the cash, with no constant taken from the data; the only bounds are the engine's own, MAX_FULL_SEARCH and
        MAX_CHANCE."""
        found = self._match(party, txn, cash, currency, balances)
        if found is None or found.rule != "REF-TEXT" or _net(
                [((i,), balances.open(i)) for i, _ in found.lines]) == cash:
            return found
        return self._netted_cited(party, txn, cash, currency, found, balances) or found

    def _netted_cited(self, party: str, txn: dict, cash: int, currency: str, cited: Proposal,
                      balances) -> Proposal | None:
        """The only set of the party's open credit notes and invoices that fell due, with the cited invoices, that adds
        up to the cash. Never credit notes alone: it needs a cited invoice. The bank cuts the text, so the cited
        invoices are a part of the batch whether or not a credit note nets in it."""
        named = {i for i, _ in cited.lines}
        if not any(i[:3] == "ARI" for i in named) or any(balances.open(i) <= 0 for i in named):
            return None  # a cited item already settled is a second payment (PARTY-DUPLICATE), not a batch
        booked = txn["booking_date"]
        pool = []
        for i in self.items.get(party, ()):
            open_cents = balances.open(i[0])
            if i[2] > booked or i[3] != currency or i[0] in named or not self.is_free(i, open_cents, balances):
                continue
            if i[0][:3] in CREDIT_NOTES or self._due.get(i[0], booked) <= booked:
                pool.append((i, open_cents))
        target = cash - _net([((i,), balances.open(i)) for i in named])
        ordered = sorted(pool, key=lambda x: (x[0][2], x[0][0]))
        signed = [(i[0], -o if i[0][:3] in CREDIT_NOTES else o) for i, o in ordered]
        if target <= 0 or len(signed) > MAX_FULL_SEARCH:
            return None
        if _chance(2 ** len(signed), [v for _, v in signed]) > MAX_CHANCE:
            return None
        chosen = _unique_subset(signed, target, 1)
        if not chosen:
            return None
        return self._proposal("PARTY-NETTED", party, [*named, *chosen], by_cash=True, confidence=0.85)

    def _credit_payout(self, txn: dict, cash: int, currency: str, balances) -> Proposal | None:
        """POLICIES §5.9: a transfer back to a customer settles its credit note, not a supplier invoice."""
        if txn["amount_cents"] >= 0 or cash <= 0:
            return None
        parties = self.parties.find(txn, "customer")
        if not self.parties.certain:
            return None
        tokens = {_alnum(t) for t in self._tokens(txn)}
        matches = []
        for party in parties:
            for note in self.items.get(party, ()):
                if (note[0][:3] != "ARC" or note[3] != currency or note[2] > txn["booking_date"]
                        or note[0] in self.reserved or balances.open(note[0]) != cash):
                    continue
                clauses = self.clauses.get(note[0], {})
                if "rappel_offset" in clauses or clauses.get("credit_refund", {}).get("mode") == "offset":
                    continue
                if note[6] in tokens or "rappel_payout" in clauses:
                    matches.append((party, note))
        if len(matches) != 1:
            return None
        party, note = matches[0]
        sources = [{"kind": "customer", "ref": party}, {"kind": "bankLine", "ref": txn["bank_txn_id"]}]
        if pdf := self.clauses.get(note[0], {}).get("_pdf"):
            sources.append({"kind": "pdf", "ref": pdf["path"]})
        return Proposal("CREDIT-PAYOUT", [(note[0], cash)], confidence=1.0, party_id=party, reference=note[1],
                        sources=sources)

    def is_free(self, item: tuple, open_cents: int, balances: OpenBalances) -> bool:
        """Open, known to be open in this phase, and not kept for the bank lines of a file."""
        return open_cents > 0 and item[2] >= self.unknown_before and (
            item[0] not in self.reserved or self._returned(item[0], balances))

    def _returned(self, item_id: str, balances: OpenBalances) -> bool:
        """A file reserves its items for its bank lines. Once the last of them has come back, the customer can pay the
        item any other way; while one is still to come (a re-presented batch), the item stays reserved."""
        history = balances.history(item_id)
        return bool(history) and history[-1]["exception"] == "RETURNED" and (
            self.reserved[item_id] <= {move["bankTxnId"] for move in history})

    def _for_another_entity(self, txn: dict, cash: int, currency: str, balances) -> Proposal | None:
        """POLICIES §5.2: a debit naming a supplier of this entity too, nothing of its here that the cash explains, and
        one supplier of that name in another entity whose open documents are the cash. Crosses entities by design: the
        evidence says which entity paid for it."""
        others = self.parties.in_other_entities(txn)
        results = [r for p in others if (r := self._match(p, txn, cash, currency, balances))]
        exact = [r for r in results if _net([((i,), balances.open(i)) for i, _ in r.lines]) == cash]
        if len(exact) != 1:
            return None
        chosen = exact[0]
        chosen.sources = [*chosen.sources, {"kind": "supplier", "ref": chosen.party_id,
                                            "label": f"paid from {txn['entity']}"}]
        return chosen

    def _in_the_group(self, parties: list[str], txn: dict, cash: int, currency: str, balances) -> Proposal | None:
        """POLICIES §5.1: a parent may pay for its subsidiaries, inside one entity. A payer named whole, with nothing of
        its own that the cash explains, and only one other customer of its group whose open documents are the cash."""
        if not self.parties.certain:
            return None
        members = {m for p in parties for m in self.parties.group_of.get(p, ())} - set(parties)
        results = [r for m in sorted(members) if (r := self._match(m, txn, cash, currency, balances))]
        exact = [r for r in results if _net([((i,), balances.open(i)) for i, _ in r.lines]) == cash]
        if len(exact) != 1:
            return None
        chosen = exact[0]
        chosen.sources = [*chosen.sources, *({"kind": "customer", "ref": p} for p in parties)]
        return chosen

    def _only_homonym_with_the_cash(self, results: list[Proposal], cash: int, currency: str,
                                    balances) -> Proposal | None:
        """Crosses customer ids, never entities: customers of one entity can share a normalized name (eleven in AU01).
        The one whose open documents are the cash to the cent settles; the others stay as candidates. Two: ask."""
        if len(results) < 2 or not self.parties.same_name([r.party_id for r in results]):
            return None
        amounts = {r.party_id: [(i, balances.open(i)) for i, _ in r.lines] for r in results}
        exact = [r for r in results if _net([((i,), o) for i, o in amounts[r.party_id]]) == cash]
        if len(exact) != 1:
            return None
        chosen = exact[0]
        chosen.candidates = [{"itemId": i, "amountCents": o, "currency": currency, "why": f"homonym {r.party_id}"}
                             for r in results if r is not chosen for i, o in amounts[r.party_id]]
        chosen.sources = [*chosen.sources, *({"kind": "customer", "ref": r.party_id} for r in results)]
        return chosen

    def _taught(self, txn: dict, kind: str, cash: int, currency: str, balances) -> Proposal | None:
        """What a person taught goes first; the amount still has to be explained, or the line goes on as usual."""
        memory = self.memory
        alias = memory.alias(txn)
        if alias:
            params, rule = alias
            target = _alnum(params.get("documentNumber") or "")
            hits = [i for i in self.by_number.get((txn["entity"], target), ()) if i[3] == currency]
            if len(hits) == 1:
                return _as_taught(self._proposal("REF-TEXT", None, [hits[0][0]], by_cash=True, confidence=1.0), rule)
            if params.get("partyId"):
                found = self._match(params["partyId"], txn, cash, currency, balances)
                if found:
                    return _as_taught(found, rule)
        hit = memory.payer(txn) or memory.paid_for(self.parties.find(txn, kind), txn["entity"])
        if hit:
            self.parties.certain = True
            found = self._match(hit[0], txn, cash, currency, balances)
            if found:
                return _as_taught(found, hit[1])
        return None

    def _abstain(self, txn: dict, reason: str, options: list[tuple[str, list[str]]], balances: OpenBalances) -> None:
        self.abstentions[txn["bank_txn_id"]] = {"reason": reason, "options": [
            {"partyId": party, "items": [(i, balances.open(i)) for i in items]} for party, items in options]}

    @staticmethod
    def _cash(txn: dict) -> tuple[int, str]:
        if txn["orig_currency"] and txn["orig_cents"]:
            return txn["orig_cents"], txn["orig_currency"]
        return abs(txn["amount_cents"]), txn["currency"]

    def _match(self, party: str, txn: dict, cash: int, currency: str, balances) -> Proposal | None:
        date = txn["booking_date"]
        mine = [i for i in self.items.get(party, ()) if i[2] <= date and i[3] == currency]
        if not mine:
            return None
        open_now = {i[0]: balances.open(i[0]) for i in mine}
        free = [(i, open_now[i[0]]) for i in mine if self.is_free(i, open_now[i[0]], balances)]
        tokens = self._tokens(txn)
        strong, weak = self._cited(mine, tokens)
        by_reference = self._by_reference(strong, weak, free, open_now, cash, party, {_alnum(t) for t in tokens})
        if by_reference:
            return by_reference
        same = [i for i, o in free if o == cash and i[0][:3] not in CREDIT_NOTES]
        if same:
            picked = self._of_month(same, txn, party) or min(same, key=lambda i: (i[2], i[0]))
            return self._proposal("PARTY-AMOUNT", party, [picked[0]], confidence=0.95 if len(same) == 1 else 0.9)
        own_note = self._invoice_less_its_note(free, cash)
        if own_note:
            return self._proposal("PARTY-NOTE-NET", party, own_note, confidence=0.9)
        tied: list[list[str]] = []
        subset = self._subset(free, cash, ambiguous=tied) if self.parties.certain else None
        if subset:
            return self._proposal("PARTY-SUBSET", party, subset, confidence=0.9)
        from .note_unit import note_units  # here: note_unit imports this module's helpers

        units = note_units(free, cash, self.credits) if self.parties.certain else None
        if units:
            return self._proposal("PARTY-NOTE-UNIT", party, [i for i, _ in units], confidence=0.85)
        block = self._consecutive(free, cash) if self.parties.certain else None
        if block:
            return self._proposal("PARTY-BLOCK", party, block, confidence=0.85)
        short = self._short_paid(free, cash, party, txn)
        if short:
            return self._proposal("PARTY-SHORT", party, [short], by_cash=True, confidence=0.85)
        self._pending += [(party, group) for group in tied]
        planned = self._explained_by_state(free, cash, party)
        if planned:
            return planned
        withheld = self._withheld(free, cash, party, set())
        if withheld:
            return self._proposal("PARTY-WITHHELD", party, withheld, by_cash=True, confidence=0.85)
        if not self.parties.certain:
            return None
        fraction = self._round_fraction(free, cash, open_now, mine)
        if fraction:
            return Proposal("PARTY-FRACTION", [(fraction, cash)], confidence=0.85, party_id=party)
        run = self._consecutive(free, cash, skipped=MAX_SKIPPED)
        if run:
            return self._proposal("PARTY-WINDOW", party, run, confidence=0.85)
        net = self._net_of_terms(free, cash, txn["booking_date"])
        if net:
            return self._proposal("PARTY-NET-SUBSET", party, net, by_cash=True, confidence=0.85)
        due_set = self._due_subset(free, cash, party, date) if not strong and not weak else None
        if due_set:
            return due_set
        # Last: what open documents can explain is more certain than a second payment of a closed one.
        return self._paid_again(mine, open_now, cash, party, balances)

    def _due_subset(self, free: list, cash: int, party: str, booked: str) -> Proposal | None:
        """A receipt citing nothing: the only set of invoices due by now, with no credit notes, that adds up to it."""
        limit = (Date.fromisoformat(booked) + timedelta(days=DUE_TOLERANCE_DAYS)).isoformat()
        pool = [(i[0], o) for i, o in sorted(free, key=lambda x: (x[0][2], x[0][0]))
                if i[0][:3] == "ARI" and o <= cash and self._due.get(i[0], "9") <= limit]
        values = [o for _, o in pool]
        if sum(values) < cash or cash * len(pool) // 8 > MAX_DUE_SEARCH_BYTES:
            return None
        sets = _sets_up_to_two(values, cash)
        if len(sets) != 1 or len(sets[0]) < 2:
            return None
        found = self._proposal("PARTY-SUBSET-DUE", party, [pool[k][0] for k in sets[0]], confidence=0.85)
        found.sources = [{"kind": "customer", "ref": party, "label": f"{len(pool)} facturas vencidas en el conjunto"}]
        return found

    @staticmethod
    def _tokens(txn: dict) -> set[str]:
        fields = (txn["text"], txn["remittance_info"], txn["end_to_end_id"], txn["ref1"], txn["ref2"])
        text = " ".join(filter(None, fields))
        return {t.strip("-/") for t in _TOKEN.findall(normalize(text.replace("/", "-")) + " " + text.upper())}

    @staticmethod
    def _cited(items: list[tuple], tokens: set[str]) -> tuple[list[tuple], list[tuple]]:
        """Items the text cites: strong (the number or a long tail) and weak (a short tail or a cut number)."""
        flats = [(token, _alnum(token)) for token in tokens]
        flats = [(t, f) for t, f in flats if len(f) >= MIN_SUFFIX]
        strong, weak = [], []
        for item in items:
            po, compact, digits, replaced = item[5], item[6], item[7], item[8]
            level = 0
            for token, flat in flats:
                if flat == compact or (po and token == po) or flat == replaced:
                    level = 2
                    break
                core = flat.lstrip("0") or flat
                if flat.isdigit() and digits.endswith(core) and len(core) >= MIN_SUFFIX:
                    level = max(level, 2 if len(core) >= STRONG_SUFFIX else 1)
                elif len(flat) >= MIN_CUT and compact.startswith(flat):
                    level = max(level, 1)
            if level == 2:
                strong.append(item)
            elif level == 1:
                weak.append(item)
        return strong, weak

    def _by_reference(self, strong: list, weak: list, free: list, open_now: dict, cash: int, party: str,
                      flats: set[str]):
        """A citation counts when it explains the cash; a whole number counts on its own."""
        make = self._proposal
        cited = [(i, open_now[i[0]]) for i in strong + weak if open_now[i[0]] > 0]
        if cited and _net(cited) == cash:
            return make("REF-TEXT", party, [i[0] for i, _ in cited], by_cash=True, confidence=1.0)
        for_strong = [(i, open_now[i[0]]) for i in strong if open_now[i[0]] > 0]
        # Fix: a subset of the citations would drop a cited invoice of the note's amount. Only whole citations: a weak
        # one says too little to net a credit note against (measured: 206 false pairs with them).
        if for_strong and _net(for_strong) > cash:
            named = {i[0] for i, _ in for_strong}
            notes = [f for f in free if f[0][0] not in named and f[0][0][:3] in CREDIT_NOTES]
            netted = self._notes_for(notes, _net(for_strong) - cash, {i[6] for i, _ in for_strong})
            if netted:
                return make("REF-COMPLETED", party, [*named, *netted], by_cash=True, confidence=0.9)
        subset = self._subset(cited, cash) if len(cited) > 1 else None
        if subset:
            return make("REF-SUBSET", party, subset, by_cash=True, confidence=0.95)
        if for_strong and _net(for_strong) < cash:
            named = {i[0] for i, _ in for_strong}
            rest = self._subset([f for f in free if f[0][0] not in named], cash - _net(for_strong), min_size=1)
            if rest:
                return make("REF-COMPLETED", party, [*named, *rest], by_cash=True, confidence=0.9)
            run = self._consecutive(free, cash, skipped=MAX_SKIPPED, named=named)
            if run:
                return make("REF-COMPLETED", party, run, by_cash=True, confidence=0.9)
        cut_number = not strong and len(cited) == 1 and any(
            len(t) >= LONG_CUT and cited[0][0][6].startswith(t) for t in flats)
        if for_strong or cut_number:
            withheld = self._withheld(free, cash, party, {i[0] for i, _ in for_strong})
            if withheld:
                return make("REF-WITHHELD", party, withheld, by_cash=True, confidence=0.9)
        if for_strong:
            return make("REF-TEXT", party, [i[0] for i, _ in for_strong], by_cash=True, confidence=0.9)
        if cut_number:
            return make("REF-TEXT", party, [cited[0][0][0]], by_cash=True, confidence=0.8)
        closed = [i for i in strong if i[4] == cash]
        if len(closed) == 1:
            return make("REF-TEXT", party, [closed[0][0]], by_cash=True, confidence=0.9)
        return None

    @staticmethod
    def _consecutive(free: list, cash: int, skipped: int = 0, named: set[str] | None = None) -> list[str] | None:
        """A single run of consecutive open invoices, by date, adding up to the cash, alone or net of one credit note,
        leaving out up to `skipped` invoices inside it (never one in `named`, which must all be in the run).

        Too many candidates for a unique subset, but exact cents make a false run very unlikely."""
        invoices = sorted((x for x in free if x[0][0][:3] not in CREDIT_NOTES), key=lambda x: (x[0][2], x[0][0]))
        if named and any(i[:3] in CREDIT_NOTES for i in named):
            return None
        ids, values = [x[0][0] for x in invoices], [x[1] for x in invoices]
        notes = [x for x in free if x[0][0][:3] in CREDIT_NOTES]
        targets = {cash: None, **{cash + o: i[0] for i, o in notes}}
        most = sum(sorted(values)[-skipped:]) if skipped else 0
        ceiling = cash + sum(o for _, o in notes) + most
        must = [ids.index(i) for i in named or () if i in ids]
        if named and len(must) != len(named):
            return None
        first, last = (min(must), max(must)) if must else (len(ids), -1)
        if skipped:
            windows = (first + 1) * (len(ids) - last) if must else len(ids) ** 2 / 2
            inside = len(ids) / 2
            if _chance(windows * (1 + inside + inside ** 2 / 2) * (1 + len(notes)), values) > MAX_CHANCE:
                return None
        found: set[tuple[frozenset, str | None]] = set()
        for start in range(min(first + 1, len(ids))):
            total = 0
            for end in range(start, len(ids)):
                total += values[end]
                if end <= start or end < last:
                    continue
                for target, note in targets.items():
                    if not 0 <= total - target <= most:
                        continue
                    for left_out in _left_out(values, start, end, total - target, skipped, must):
                        found.add((frozenset(ids[k] for k in range(start, end + 1) if k not in left_out), note))
                if total > ceiling or len(found) > 1:
                    break
            if len(found) > 1:
                return None
        if len(found) != 1:
            return None
        run, note = found.pop()
        return sorted(run) + [note] if note else sorted(run)

    def _notes_for(self, notes: list, gap: int, cited: set[str]) -> list[str] | None:
        """Credit notes, not cited, that are exactly what the customer netted from the invoices it cites. Those that
        name a cited invoice go first (POLICIES §5.9)."""
        own = [n for n in notes if self.credits.get(n[0][0]) in cited]
        if own and sum(n[1] for n in own) == gap:
            return [n[0][0] for n in own]
        exact = [n[0][0] for n in notes if n[1] == gap]
        if len(exact) == 1:
            return exact
        if len(exact) > 1 or len(notes) > MAX_FULL_SEARCH:
            return None
        positive = [((n[0][0], "", "", "", 0, "", "", "", ""), n[1]) for n in notes]
        return _unique_subset([(i[0], o) for i, o in positive], gap, 2) if positive else None

    def _invoice_less_its_note(self, free: list, cash: int) -> list[str] | None:
        """No citation, and the only invoice that, less the credit note that names it, is the cash (POLICIES §5.9)."""
        invoices = {i[6]: (i[0], o) for i, o in free if i[0][:3] not in CREDIT_NOTES}
        found = []
        for note, note_open in free:
            credited = invoices.get(self.credits.get(note[0], ""))
            if note[0][:3] in CREDIT_NOTES and credited and credited[1] - note_open == cash:
                found.append([credited[0], note[0]])
        return found[0] if len(found) == 1 else None

    def _of_month(self, same: list, txn: dict, party: str) -> tuple | None:
        """Equal amounts: the text names a month. The PDF names the invoice's; else it is issued the month after."""
        party_words = {word for name in self.parties.names_of[party] for word in name.split()}
        named = _month_of(normalize(f"{txn['text'] or ''} {txn['remittance_info'] or ''}"), party_words)
        if named is None or len(same) < 2:
            return None
        month, year = named
        by_pdf = [i for i in same if self._is_month(self.clauses.get(i[0], {}).get("service_month"), month, year)]
        if by_pdf:
            return min(by_pdf, key=lambda i: (i[2], i[0]))
        following = month % 12 + 1
        by_issue = [i for i in same
                    if int(i[2][5:7]) == following and "service_month" not in self.clauses.get(i[0], {})]
        return min(by_issue, key=lambda i: (i[2], i[0])) if by_issue else None

    @staticmethod
    def _is_month(clause: dict | None, month: int, year: int | None) -> bool:
        return bool(clause) and clause["month"] == month and (year is None or clause["year"] == year)

    def _net_of_terms(self, free: list, cash: int, booked: str) -> list[str] | None:
        """Several invoices, each net of its early-payment discount within terms (POLICIES §3). One unique set. Net of a
        withheld rate it took SHORT_WITHHOLDING below its gate in the drift holdout: left out."""

        def paid(item: tuple, open_cents: int) -> int:
            pct = self.terms_pct.get(item[0])
            terms = Terms(pct, self.discount_days.get(item[0]), item[2], item[4])
            if open_cents != item[4] or not _in_terms(terms, booked):
                return open_cents
            return open_cents - round(item[4] * pct / 100)

        credit = sum(o for i, o in free if i[0][:3] in CREDIT_NOTES)
        signed = [(i[0], -o if i[0][:3] in CREDIT_NOTES else paid(i, o)) for i, o in free]
        if all(v == o or i[0][:3] in CREDIT_NOTES for (i, o), (_, v) in zip(free, signed, strict=True)):
            return None
        signed = [(i, v) for i, v in signed if v <= cash + credit]
        if not 2 <= len(signed) <= MAX_FULL_SEARCH or (
                _chance(2 ** len(signed), [v for _, v in signed]) > MAX_CHANCE):
            return None
        return _unique_subset(signed, cash, 2)

    def _withheld(self, free: list, cash: int, party: str, named: set[str]) -> list[str] | None:
        """The one set of open documents, with the ones the text names, whose invoices net of a tax rate are the cash.

        Why it generalizes: POLICIES §3 fixes who withholds (customers of Mexico, Brazil and Morocco) and at which rates
        (1.25 %, 1.5 %, 10 %) and clears the invoice in full; the official example ar_short_withholding pays four
        invoices at 0.90 of their sum, with a text that cites none. Nothing here comes from one customer or one phase:
        the country is the master's, the rates the policy's, and a set only counts within MAX_CHANCE. The example's
        written trap ("only on the item that suffers it") contradicts its own rows and the golden, which mark them all.
        An invoice whose PDF explains its own shortfall (POLICIES §5.8) is not taxed here: that clause wins."""
        if self.countries.get(party) not in WITHHOLDING_COUNTRIES:
            return None
        invoices = [(i[0], o) for i, o in free if i[0][:3] not in CREDIT_NOTES and o == i[4]
                    and not OWN_SHORTFALL & self.clauses.get(i[0], {}).keys()]
        notes = [(i[0], -o) for i, o in free if i[0][:3] in CREDIT_NOTES]
        credit = -sum(v for _, v in notes)
        found: set[frozenset[str]] = set()
        for rate in WITHHOLDING_RATES:
            net = [(i, o - round(o * rate)) for i, o in invoices]
            signed = [x for x in net if x[1] <= cash + credit + 1] + notes
            must = [v for i, v in signed if i in named]
            rest = [x for x in signed if x[0] not in named]
            searched = 2 ** len(rest) * len(WITHHOLDING_RATES) * len(ROUNDING_CENTS)
            if (len(must) != len(named) or len(rest) > MAX_FULL_SEARCH
                    or _chance(searched, [v for _, v in rest]) > MAX_CHANCE):
                continue
            for cents in ROUNDING_CENTS:
                target = cash + cents - sum(must)
                subset = [] if named and target == 0 else _unique_subset(rest, target, 1)
                if subset is not None:
                    found.add(frozenset((*subset, *named)))
        if len(found) != 1:
            return None
        chosen = sorted(found.pop())
        paid = [f for f in free if f[0][0] in chosen]
        others = [f for f in free if f[0][0][:3] in CREDIT_NOTES and f[0][0] not in chosen]
        if self._notes_for(others, _net(paid) - cash, {i[6] for i, _ in paid}):  # a note of that difference: not tax
            return None
        return chosen if any(i[:3] not in CREDIT_NOTES for i in chosen) else None

    def _paid_again(self, mine: list, open_now: dict, cash: int, party: str, balances) -> Proposal | None:
        """A whole party, nothing open that the cash explains, and one invoice with exactly that total that a line of
        this run settled. One closed before the run may only look like the cash (POLICIES §3, unidentified)."""
        closed = [i for i in mine if open_now[i[0]] <= 0 and i[4] == cash and i[0][:3] not in CREDIT_NOTES]
        if len(closed) != 1 or not balances.history(closed[0][0]):
            return None
        return self._proposal("PARTY-DUPLICATE", party, [closed[0][0]], by_cash=True, confidence=0.85)

    def _explained_by_state(self, free: list, cash: int, party: str) -> Proposal | None:
        """No exact amount: only what the invoice's own PDF expects. Anything looser was measured and rejected."""
        invoices = [(i, o) for i, o in free if i[0][:3] not in CREDIT_NOTES]
        planned = [i for i, _ in invoices if self._plan_expects(i, cash)]
        if planned:
            item_id = min(planned, key=lambda i: (i[2], i[0]))[0]
            found = self._proposal("PARTY-PLAN", party, [item_id], by_cash=True, confidence=0.9)
            if pdf := self.clauses[item_id].get("_pdf"):
                found.sources.append({"kind": "pdf", "ref": pdf["path"]})
            return found
        return None

    def _round_fraction(self, free: list, cash: int, open_now: dict, mine: list) -> str | None:
        """The one whole open invoice of which the cash is a round share, to the cent. Not one with an open credit
        note of its own: notes are round shares too, and the invoice net of one only looks like a partial."""
        noted = {self.related.get(i[0]) for i in mine if i[0][:3] in CREDIT_NOTES and open_now[i[0]] > 0}
        # Its PDF says what is short and why: only `_plan_expects` can read that cash.
        whole = [i for i, o in free if i[0][:3] not in CREDIT_NOTES and o == i[4] > cash and i[6] not in noted
                 and not {"retention", "advance_deduction"} & self.clauses.get(i[0], {}).keys()]
        # Each invoice spreads its shares over its own total: how many would land on any cash by chance.
        if sum(_chance((ROUND_FRACTIONS - 1) * SHARE_WINDOW, [i[4]]) for i in whole) > MAX_CHANCE:
            return None
        hits = [i[0] for i in whole if any(
            abs(cash * ROUND_FRACTIONS - i[4] * k) <= ROUND_FRACTIONS for k in range(1, ROUND_FRACTIONS))]
        return hits[0] if len(hits) == 1 else None

    def _plan_expects(self, item: tuple, cash: int) -> bool:
        clauses = self.clauses.get(item[0])
        if not clauses:
            return False
        if cash in clauses.get("instalments", {}).get("amounts", ()):
            return True
        return document_says(clauses, item[4], cash) is not None

    def _by_number_alone(self, txn: dict, cash: int, currency: str, balances) -> Proposal | None:
        """A whole number in the text and an amount that agrees: enough without knowing who paid."""
        hits = {}
        wanted = ("AR" if txn["amount_cents"] > 0 else "AP")
        for token in self._tokens(txn):
            for item in self.by_number.get((txn["entity"], _alnum(token)), ()):
                if item[3] == currency and item[2] <= txn["booking_date"] and item[0][:2] == wanted:
                    hits[item[0]] = item
        if not hits:
            return None
        items = list(hits.values())
        cited = [(i, balances.open(i[0])) for i in items]
        agrees = _net(cited) == cash
        if len(items) == 1 and not agrees:
            open_cents = cited[0][1]
            agrees = (open_cents <= 0 and items[0][4] == cash) or (
                open_cents > 0 and abs(open_cents - cash) <= open_cents * NUMBER_ALONE_TOLERANCE)
        if not agrees:
            return None
        return self._proposal("REF-NUMBER", None, [i[0] for i in items], by_cash=True, confidence=0.95)

    @staticmethod
    def _subset(free: list, cash: int, min_size: int = 2, ambiguous: list | None = None) -> list[str] | None:
        """A unique set of items, net of credit notes, that adds up exactly to the cash. With a list in `ambiguous`,
        small sets that tie are left there for a person to decide; nothing reads them to choose."""
        ordered = sorted(free, key=lambda x: (x[0][2], x[0][0]))
        credit = sum(o for i, o in ordered if i[0][:3] in CREDIT_NOTES)
        # An invoice above the cash plus every credit note cannot be part of it.
        signed_all = [(i[0], -o if i[0][:3] in CREDIT_NOTES else o) for i, o in ordered
                      if i[0][:3] in CREDIT_NOTES or o <= cash + credit]
        if len(signed_all) <= ALWAYS_SEARCHED or (len(signed_all) <= MAX_FULL_SEARCH and _chance(
                2 ** len(signed_all), [v for _, v in signed_all]) <= MAX_CHANCE):
            found = _unique_subset(signed_all, cash, min_size)
            if found is None and ambiguous is not None:
                ambiguous += _tied_subsets(signed_all, cash)
            return found
        running = 0
        for n, (_, value) in enumerate(signed_all, 1):
            running += value
            if running == cash and n >= max(min_size, 2):
                return [i for i, _ in signed_all[:n]]
        return _small_subset(signed_all[:MAX_SUBSET_ITEMS], cash, min_size)

    def _short_paid(self, free: list, cash: int, party: str, txn: dict) -> str | None:
        hits = []
        from_abroad = cross_border(txn.get("bank_code"), txn["text"])
        foreign_payer = from_abroad and party in self.countries and self.countries[party] not in SEPA_COUNTRIES
        eur_per_cent = abs(txn["amount_eur_cents"]) / abs(txn["amount_cents"]) if txn.get("amount_eur_cents") else 1.0
        for item, open_cents in free:
            if item[0][:3] in CREDIT_NOTES or open_cents != item[4]:
                continue
            # Its PDF says what is short and why: only `_plan_expects` can read that cash.
            if {"retention", "advance_deduction"} & self.clauses.get(item[0], {}).keys():
                continue
            pct = self.terms_pct.get(item[0])
            if pct and abs(item[4] - round(item[4] * pct / 100) - cash) <= 1:
                hits.append(item[0])
            elif any(abs(item[4] - round(item[4] * r) - cash) <= 1 for r in _WITHHOLDING):
                hits.append(item[0])
            elif (foreign_payer or fee_stated(txn["text"], txn["currency"], item[4] - cash)) and (
                    0 < item[4] - cash <= item[4] * FEE_LIMIT_RATIO) and (
                    (item[4] - cash) * eur_per_cent <= FEE_LIMIT_EUR_CENTS) and fee_fits(
                    txn["text"], txn["currency"], item[4] - cash):
                hits.append(item[0])
        return hits[0] if len(hits) == 1 else None

    @staticmethod
    def _proposal(rule: str, party: str | None, items: list[str], *, by_cash: bool = False,
                  confidence: float) -> Proposal:
        return Proposal(rule=rule, lines=[(i, None) for i in sorted(items)], confidence=confidence, party_id=party,
                        by_cash=by_cash)

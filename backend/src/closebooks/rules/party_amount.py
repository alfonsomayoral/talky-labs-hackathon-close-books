"""R3 and R4, evaluated by booking date: the party, its items open at that moment and the numbers the text cites."""
from __future__ import annotations

import re
from collections import defaultdict
from itertools import combinations

import polars as pl

from ..documents.pdfs import phase_clauses
from ..load import cancelled_item_ids
from ..model import Proposal
from ..policy import FEE_LIMIT_EUR_CENTS, FEE_LIMIT_RATIO, SEPA_COUNTRIES, cross_border
from ..state import OpenBalances
from .parties import PartyIndex, normalize

_TOKEN = re.compile(r"[A-Z0-9][A-Z0-9/\-]{2,}")
MIN_SUFFIX = 3
STRONG_SUFFIX = 5
MIN_CUT = 6
LONG_CUT = 8
MAX_SUBSET_ITEMS = 24
MAX_FULL_SEARCH = 16  # beyond this, sums collide so often that a unique subset means nothing
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


def _net(pairs: list) -> int:
    return sum(-o if i[0][:3] in CREDIT_NOTES else o for i, o in pairs)


def _clauses(phase) -> dict[str, dict[str, dict]]:
    """Facts of the invoice PDFs per item. Parsers extract them; only the rules below decide with them."""
    if not hasattr(phase, "dir") or not (phase.dir / "pdfs" / "index.csv").exists():
        return {}
    facts = phase_clauses(phase)
    return {item: {c.kind: c.value for c in doc.clauses} for item, doc in facts._by_item.items() if doc.clauses}


def _month_of(text: str) -> tuple[int, int | None] | None:
    for match in _MONTH.finditer(text):
        year = match[2]
        return MONTHS[match[1]], (2000 + int(year) % 100) if year else None
    return None


class PartyAmount:
    def __init__(self, phase, reserved: set[str]):
        self.reserved = reserved
        self.clauses = _clauses(phase)
        self.cancelled = cancelled_item_ids(phase.items) if "reason" in phase.items.columns else set()
        # bank_txn_id -> why the engine proposed nothing although it had evidence: nobody reads this to decide
        self.abstentions: dict[str, dict] = {}
        self._pending: list[tuple[str, list[str]]] = []
        items = phase.items
        # TRAIN has no opening balances: items issued before its first line are candidates only if something cites them.
        self.unknown_before = phase.start if getattr(phase, "name", "") == "train" else ""
        self.terms_pct = _discount_pct(phase)
        customers = phase.masters["customers"]
        self.countries = dict(customers.select("customer_id", "country").iter_rows()) if (
            "country" in customers.columns) else {}
        known = items.filter(pl.col("party_id").is_not_null())
        self.parties = PartyIndex(phase.masters, known.select("entity", "party_id", "party_name").unique())
        self._known = known
        self.reindex()

    def release(self) -> None:
        """Before writing the run: the indexes are the biggest thing in memory and nothing needs them after resolve."""
        self.items, self.by_number, self.clauses = {}, {}, {}
        self.parties = None
        self._known = None

    def reindex(self) -> None:
        self.items: dict[str, list[tuple]] = defaultdict(list)
        self.by_number: dict[tuple[str, str], list[tuple]] = defaultdict(list)
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

    def __call__(self, txn: dict, balances: OpenBalances) -> Proposal | None:
        kind = "customer" if txn["amount_cents"] > 0 else "supplier"
        parties = self.parties.find(txn, kind)
        cash, currency = self._cash(txn)
        self._pending = []
        results = [r for party in parties if (r := self._match(party, txn, cash, currency, balances))]
        if len(results) == 1:
            return results[0]
        found = self._by_number_alone(txn, cash, currency, balances)
        if found:
            return found
        if results:
            self._abstain(txn, "parties", [(r.party_id, [i for i, _ in r.lines]) for r in results], balances)
        elif self._pending:
            self._abstain(txn, "subsets", self._pending, balances)
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
        free = [(i, open_now[i[0]]) for i in mine
                if open_now[i[0]] > 0 and i[0] not in self.reserved and i[2] >= self.unknown_before]
        tokens = self._tokens(txn)
        strong, weak = self._cited(mine, tokens)
        by_reference = self._by_reference(strong, weak, free, open_now, cash, party, {_alnum(t) for t in tokens})
        if by_reference:
            return by_reference
        same = [i for i, o in free if o == cash and i[0][:3] not in CREDIT_NOTES]
        if same:
            picked = self._of_month(same, txn) or min(same, key=lambda i: (i[2], i[0]))
            return self._proposal("PARTY-AMOUNT", party, [picked[0]], confidence=0.95 if len(same) == 1 else 0.9)
        tied: list[list[str]] = []
        subset = self._subset(free, cash, ambiguous=tied) if self.parties.certain else None
        if subset:
            return self._proposal("PARTY-SUBSET", party, subset, confidence=0.9)
        block = self._consecutive(free, cash) if self.parties.certain else None
        if block:
            return self._proposal("PARTY-BLOCK", party, block, confidence=0.85)
        short = self._short_paid(free, cash, party, txn)
        if short:
            return self._proposal("PARTY-SHORT", party, [short], by_cash=True, confidence=0.85)
        self._pending += [(party, group) for group in tied]
        return self._explained_by_state(free, cash, party)

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
        subset = self._subset(cited, cash) if len(cited) > 1 else None
        if subset:
            return make("REF-SUBSET", party, subset, by_cash=True, confidence=0.95)
        for_strong = [(i, open_now[i[0]]) for i in strong if open_now[i[0]] > 0]
        if for_strong and _net(for_strong) > cash:
            named = {i[0] for i, _ in for_strong}
            notes = [f for f in free if f[0][0] not in named and f[0][0][:3] in CREDIT_NOTES]
            netted = self._notes_for(notes, _net(for_strong) - cash)
            if netted:
                return make("REF-COMPLETED", party, [*named, *netted], by_cash=True, confidence=0.9)
        if for_strong and _net(for_strong) < cash:
            named = {i[0] for i, _ in for_strong}
            rest = self._subset([f for f in free if f[0][0] not in named], cash - _net(for_strong), min_size=1)
            if rest:
                return make("REF-COMPLETED", party, [*named, *rest], by_cash=True, confidence=0.9)
        if for_strong:
            return make("REF-TEXT", party, [i[0] for i, _ in for_strong], by_cash=True, confidence=0.9)
        if not strong and len(cited) == 1 and any(len(t) >= LONG_CUT and cited[0][0][6].startswith(t) for t in flats):
            return make("REF-TEXT", party, [cited[0][0][0]], by_cash=True, confidence=0.8)
        closed = [i for i in strong if i[4] == cash]
        if len(closed) == 1:
            return make("REF-TEXT", party, [closed[0][0]], by_cash=True, confidence=0.9)
        return None

    @staticmethod
    def _consecutive(free: list, cash: int) -> list[str] | None:
        """A single run of consecutive open invoices, by date, adding up to the cash, alone or net of one credit note.

        Too many candidates for a unique subset, but exact cents make a false run very unlikely."""
        invoices = sorted((x for x in free if x[0][0][:3] not in CREDIT_NOTES), key=lambda x: (x[0][2], x[0][0]))
        notes = [x for x in free if x[0][0][:3] in CREDIT_NOTES]
        targets = {cash: None, **{cash + o: i[0] for i, o in notes}}
        found = []
        for start in range(len(invoices)):
            total = 0
            for end in range(start, len(invoices)):
                total += invoices[end][1]
                if total in targets and end > start:
                    found.append((start, end, targets[total]))
                if total > cash + sum(o for _, o in notes):
                    break
        if len(found) != 1:
            return None
        start, end, note = found[0]
        block = [invoices[k][0][0] for k in range(start, end + 1)]
        return [*block, note] if note else block

    @staticmethod
    def _notes_for(notes: list, gap: int) -> list[str] | None:
        """Credit notes, not cited, that are exactly what the customer netted from the invoices it cites."""
        exact = [n[0][0] for n in notes if n[1] == gap]
        if len(exact) == 1:
            return exact
        if len(exact) > 1 or len(notes) > MAX_FULL_SEARCH:
            return None
        positive = [((n[0][0], "", "", "", 0, "", "", "", ""), n[1]) for n in notes]
        return _unique_subset([(i[0], o) for i, o in positive], gap, 2) if positive else None

    def _of_month(self, same: list, txn: dict) -> tuple | None:
        """Equal amounts: the text names a month. The PDF names the invoice's; else it is issued the month after."""
        named = _month_of(normalize(f"{txn['text'] or ''} {txn['remittance_info'] or ''}"))
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

    def _explained_by_state(self, free: list, cash: int, party: str) -> Proposal | None:
        """No exact amount: only what the invoice's own PDF expects. Anything looser was measured and rejected."""
        invoices = [(i, o) for i, o in free if i[0][:3] not in CREDIT_NOTES]
        planned = [i for i, _ in invoices if self._plan_expects(i[0], cash)]
        if planned:
            return self._proposal("PARTY-PLAN", party, [min(planned, key=lambda i: (i[2], i[0]))[0]], by_cash=True,
                                  confidence=0.9)
        return None

    def _plan_expects(self, item_id: str, cash: int) -> bool:
        clauses = self.clauses.get(item_id)
        if not clauses:
            return False
        if cash in clauses.get("instalments", {}).get("amounts", ()):
            return True
        return cash in (clauses.get("retention", {}).get("payableCents"),
                        clauses.get("advance_deduction", {}).get("netDueCents"))

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
        if len(signed_all) <= MAX_FULL_SEARCH:
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
            pct = self.terms_pct.get(item[0])
            if pct and abs(item[4] - round(item[4] * pct / 100) - cash) <= 1:
                hits.append(item[0])
            elif any(abs(item[4] - round(item[4] * r) - cash) <= 1 for r in _WITHHOLDING):
                hits.append(item[0])
            elif foreign_payer and 0 < item[4] - cash <= item[4] * FEE_LIMIT_RATIO and (
                    (item[4] - cash) * eur_per_cent <= FEE_LIMIT_EUR_CENTS):
                hits.append(item[0])
        return hits[0] if len(hits) == 1 else None

    @staticmethod
    def _proposal(rule: str, party: str | None, items: list[str], *, by_cash: bool = False,
                  confidence: float) -> Proposal:
        return Proposal(rule=rule, lines=[(i, None) for i in sorted(items)], confidence=confidence, party_id=party,
                        by_cash=by_cash)

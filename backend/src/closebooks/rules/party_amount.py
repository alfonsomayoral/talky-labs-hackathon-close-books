"""R3 and R4, evaluated by booking date: the party, its items open at that moment and the numbers the text cites."""
from __future__ import annotations

import re
from collections import defaultdict

import polars as pl

from ..model import Proposal
from ..policy import FEE_LIMIT_EUR_CENTS, FEE_LIMIT_RATIO, SEPA_COUNTRIES, cross_border
from ..state import OpenBalances
from .parties import PartyIndex, normalize

_TOKEN = re.compile(r"[A-Z0-9][A-Z0-9/\-]{2,}")
MIN_SUFFIX = 3
STRONG_SUFFIX = 5
MIN_CUT = 6
MAX_SUBSET_ITEMS = 24
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


def _net(pairs: list) -> int:
    return sum(-o if i[0][:3] in CREDIT_NOTES else o for i, o in pairs)


class PartyAmount:
    def __init__(self, phase, reserved: set[str]):
        self.reserved = reserved
        items = phase.items
        # TRAIN has no opening balances: items issued before its first line are candidates only if something cites them.
        self.unknown_before = phase.start if getattr(phase, "name", "") == "train" else ""
        self.terms_pct = _discount_pct(phase)
        customers = phase.masters["customers"]
        self.countries = dict(customers.select("customer_id", "country").iter_rows()) if (
            "country" in customers.columns) else {}
        known = items.filter(pl.col("party_id").is_not_null())
        self.parties = PartyIndex(phase.masters, known.select("entity", "party_id", "party_name").unique())
        self.items: dict[str, list[tuple]] = defaultdict(list)
        columns = ("item_id", "party_id", "document_number", "issue_date", "currency", "total_cents", "customer_po")
        for item_id, party, number, issued, currency, total, po in known.select(columns).iter_rows():
            compact = _alnum(number or "")
            self.items[party].append((item_id, number or "", issued or "", currency, total, (po or "").upper(), compact,
                                      re.sub(r"\D", "", number or "")))

    def __call__(self, txn: dict, balances: OpenBalances) -> Proposal | None:
        kind = "customer" if txn["amount_cents"] > 0 else "supplier"
        parties = self.parties.find(txn, kind)
        if not parties:
            return None
        cash, currency = self._cash(txn)
        results = [r for party in parties if (r := self._match(party, txn, cash, currency, balances))]
        if len(results) != 1:
            return None
        return results[0]

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
        strong, weak = self._cited(mine, self._tokens(txn))
        by_reference = self._by_reference(strong, weak, free, open_now, cash, party)
        if by_reference:
            return by_reference
        same = [i for i, o in free if o == cash and i[0][:3] not in CREDIT_NOTES]
        if same:
            oldest = min(same, key=lambda i: (i[2], i[0]))
            return self._proposal("PARTY-AMOUNT", party, [oldest[0]], confidence=0.95 if len(same) == 1 else 0.9)
        subset = self._subset(free, cash)
        if subset:
            return self._proposal("PARTY-SUBSET", party, subset, confidence=0.9)
        short = self._short_paid(free, cash, party, txn)
        if short:
            return self._proposal("PARTY-SHORT", party, [short], by_cash=True, confidence=0.85)
        return None

    @staticmethod
    def _tokens(txn: dict) -> set[str]:
        fields = (txn["text"], txn["remittance_info"], txn["end_to_end_id"], txn["ref1"], txn["ref2"])
        text = " ".join(filter(None, fields))
        return {t.strip("-/") for t in _TOKEN.findall(normalize(text.replace("/", "-")) + " " + text.upper())}

    @staticmethod
    def _cited(items: list[tuple], tokens: set[str]) -> tuple[list[tuple], list[tuple]]:
        """Items the text cites: strong (the number, whole or barely cut) and weak (a short tail or a cut number)."""
        flats = [(token, _alnum(token)) for token in tokens]
        flats = [(t, f) for t, f in flats if len(f) >= MIN_SUFFIX]
        strong, weak = [], []
        for item in items:
            po, compact, digits = item[5], item[6], item[7]
            level = 0
            for token, flat in flats:
                if flat == compact or (po and token == po):
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

    def _by_reference(self, strong: list, weak: list, free: list, open_now: dict, cash: int, party: str):
        """A citation counts when it explains the cash; a whole number counts on its own."""
        make = self._proposal
        cited = [(i, open_now[i[0]]) for i in strong + weak if open_now[i[0]] > 0]
        if cited and _net(cited) == cash:
            return make("REF-TEXT", party, [i[0] for i, _ in cited], by_cash=True, confidence=1.0)
        subset = self._subset(cited, cash) if len(cited) > 1 else None
        if subset:
            return make("REF-SUBSET", party, subset, by_cash=True, confidence=0.95)
        for_strong = [(i, open_now[i[0]]) for i in strong if open_now[i[0]] > 0]
        if for_strong and _net(for_strong) < cash:
            named = {i[0] for i, _ in for_strong}
            rest = self._subset([f for f in free if f[0][0] not in named], cash - _net(for_strong), min_size=1)
            if rest:
                return make("REF-COMPLETED", party, [*named, *rest], by_cash=True, confidence=0.9)
        if for_strong:
            return make("REF-TEXT", party, [i[0] for i, _ in for_strong], by_cash=True, confidence=0.9)
        closed = [i for i in strong if i[4] == cash]
        if len(closed) == 1:
            return make("REF-TEXT", party, [closed[0][0]], by_cash=True, confidence=0.9)
        return None

    @staticmethod
    def _subset(free: list, cash: int, min_size: int = 2) -> list[str] | None:
        """A unique set of up to four items, net of credit notes, that adds up exactly to the cash."""
        pool = sorted(free, key=lambda x: (x[0][2], x[0][0]))[:MAX_SUBSET_ITEMS]
        signed = [(i[0], -o if i[0][:3] in CREDIT_NOTES else o) for i, o in pool]
        singles: dict[int, list[str]] = defaultdict(list)
        for item, value in signed:
            singles[value].append(item)
        if min_size == 1 and singles.get(cash):
            return singles[cash][:1] if len(singles[cash]) == 1 else None
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
    def _proposal(rule: str, party: str, items: list[str], *, by_cash: bool = False, confidence: float) -> Proposal:
        return Proposal(rule=rule, lines=[(i, None) for i in items], confidence=confidence, party_id=party,
                        by_cash=by_cash)

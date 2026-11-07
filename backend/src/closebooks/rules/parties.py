"""Who paid: from the ordering party, the account or the name inside the bank text (POLICIES §5.5)."""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

import polars as pl

MIN_NAME_CHARS = 10
PREFIX_CHARS = 8
# Words of a company's legal form, in any of the group's markets. What is left after them is the name.
LEGAL_FORMS = frozenset("""
S A L U C V R DE RL COOP SA SL SLU SAS SARL EURL GMBH CO KG AG EK E LTD LTDA LLC LLP INC CORP PTY BV NV SRL SNC SPA
SP Z O OO EIRELI ME EPP GROUP PLC
""".split())
_NOT_ALNUM = re.compile(r"[^A-Z0-9]+")


def normalize(text: str | None) -> str:
    if not text:
        return ""
    upper = text.upper()
    plain = upper if upper.isascii() else "".join(
        c for c in unicodedata.normalize("NFKD", upper) if not unicodedata.combining(c))
    return _NOT_ALNUM.sub(" ", plain).strip()


class PartyIndex:
    certain = False

    def __init__(self, masters: dict[str, pl.DataFrame], printed: pl.DataFrame):
        self.by_name: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        self.by_iban: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        self.by_prefix: dict[tuple[str, str, str], list[tuple[str, str]]] = defaultdict(list)
        self.names_of: dict[str, set[str]] = defaultdict(set)
        self.group_of: dict[str, list[str]] = {}
        self.entities: set[str] = set()
        customers = masters["customers"]
        for row in customers.iter_rows(named=True):
            self._add("customer", row["entity"], row["customer_id"], row["name"], row["iban"])
            if row["trade_name"]:
                self._add("customer", row["entity"], row["customer_id"], row["trade_name"], None)
        for row in masters["suppliers"].iter_rows(named=True):
            self._add("supplier", row["entity"], row["supplier_id"], row["name"], row["iban"])
        for entity, party, name in printed.select("entity", "party_id", "party_name").iter_rows():
            kind = "supplier" if party and party.startswith("S") else "customer"
            self._add(kind, entity, party, name, None)
        members: dict[tuple[str, str], list[str]] = defaultdict(list)
        columns = ("customer_id", "entity", "group_id", "parent_customer_id")
        for row in customers.select(columns).iter_rows(named=True):
            key = row["group_id"] or row["parent_customer_id"]
            if key:
                members[row["entity"], key].append(row["customer_id"])
        for row in customers.select(columns).iter_rows(named=True):
            key = row["group_id"] or row["parent_customer_id"]
            if key:
                self.group_of[row["customer_id"]] = members[row["entity"], key]

    def _add(self, kind: str, entity: str, party: str, name: str | None, iban: str | None) -> None:
        self.entities.add(entity)
        norm = normalize(name)
        if norm:
            self.names_of[party].add(norm)
            key = (kind, entity, norm)
            if party not in self.by_name[key]:
                self.by_name[key].add(party)
                self.by_prefix[kind, entity, norm[:PREFIX_CHARS]].append((norm, party))
        if iban:
            self.by_iban[kind, entity, iban].add(party)

    def in_other_entities(self, txn: dict) -> list[str]:
        """POLICIES §5.2: the supplier a group treasury pays may be another entity's. Only the whole name counts."""
        name = normalize(txn.get("counterparty_name"))
        found: set[str] = set()
        for other in sorted(self.entities - {txn["entity"]}):
            found |= self.by_name.get(("supplier", other, name), set())
            found |= set(self._in_text(txn, "supplier", other, name, whole_only=True))
        self.certain = False
        return sorted(found)

    def same_name(self, parties: list[str]) -> bool:
        return bool(set.intersection(*(self.names_of[p] for p in parties)))

    def find(self, txn: dict, kind: str) -> list[str]:
        """The parties the line names. `self.certain` says whether the evidence was whole: a known ordering party, its
        account or the full name, not a name the bank cut."""
        self.certain = True
        entity = txn["entity"]
        name = normalize(txn.get("counterparty_name"))
        if name and (found := self.by_name.get((kind, entity, name))):
            return sorted(found)
        iban = txn.get("counterparty_account")
        if iban and (found := self.by_iban.get((kind, entity, iban))):
            return sorted(found)
        found = self._in_text(txn, kind, entity, name, whole_only=bool(name))
        if found or kind != "supplier":
            return found
        # The group's treasury pays invoices of its subsidiaries (POLICIES §5.2): the supplier may be another entity's.
        for other in sorted(self.entities - {entity}):
            found += self._in_text(txn, kind, other, name, whole_only=bool(name))
        self.certain = False
        return sorted(set(found))

    def _in_text(self, txn: dict, kind: str, entity: str, name: str, whole_only: bool) -> list[str]:
        """The party named in the text. With an unknown ordering party it may be paying for someone else (confirming),
        but then a similar name proves nothing: only the whole name counts."""
        raw = txn.get("text") or ""
        # N43 cuts a word at the 38-character boundary and joins the fields with " | ".
        glued = normalize(raw.replace(" | ", ""))
        spaced = normalize(raw)
        best: dict[str, int] = {}
        whole: dict[str, int] = {}
        for text in {glued, spaced}:
            for position in _word_starts(text):
                for norm, party in self.by_prefix.get((kind, entity, text[position:position + PREFIX_CHARS]), ()):
                    length = _common_prefix(norm, text, position)
                    if length == len(norm) or (not whole_only and _identifies(norm, text, position, length)):
                        best[party] = max(best.get(party, 0), length)
                        if length == len(norm):
                            whole[party] = max(whole.get(party, 0), length)
        if not best:
            return []
        top = max(best.values())
        self.certain = all(top == w for p, w in whole.items() if best.get(p) == top) and any(
            best.get(p) == top for p in whole)
        return sorted(p for p, length in best.items() if length == top)


def _word_starts(text: str) -> list[int]:
    return [0, *[i + 1 for i, c in enumerate(text) if c == " "]] if text else []


def _common_prefix(a: str, b: str, start: int) -> int:
    n = 0
    for x, y in zip(a, b[start:], strict=False):
        if x != y:
            break
        n += 1
    return n


def _identifies(norm: str, text: str, position: int, length: int) -> bool:
    """The whole name; one the bank cut, the text ending or starting another word where the name stops mid-word
    ("PLASTICOS EXPRES | RECIBO"); or the name without its legal form."""
    if length == len(norm):
        return True
    if length < MIN_NAME_CHARS:
        return False
    end = position + length
    if end == len(text) or all(word in LEGAL_FORMS for word in norm[length:].split()):
        return True
    return norm[length - 1] != " " and text[end] == " "

"""What a person taught on an earlier run (CONTRACT §4): applied first, with the rule as its evidence."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .model import Proposal
from .rules.parties import normalize

APPLIED_KINDS = ("payer_is_customer", "parent_pays", "reference_alias", "always_category")
RULE = "MEMORY-RULE"


def load_rules(folder: Path | None) -> list[dict]:
    """Active rules of `human/memory_rules.jsonl`. The last record of a ruleId wins: that is how the API deletes."""
    path = Path(folder) / "memory_rules.jsonl" if folder else None
    if path is None or not path.exists():
        return []
    latest: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        if line.strip():
            rule = json.loads(line)
            latest[rule["ruleId"]] = rule
    return [r for r in latest.values() if r.get("active", True)]


def evidence(rule: dict) -> list[dict]:
    return [{"kind": "memoryRule", "ref": rule["ruleId"]}]


def _in_scope(rule: dict, entity: str | None) -> bool:
    wanted = (rule.get("scope") or {}).get("entity")
    return not wanted or wanted == entity


class Memory:
    def __init__(self, rules: list[dict]):
        self.rules = rules
        self.ignored = [r["ruleId"] for r in rules if r["kind"] not in APPLIED_KINDS]
        self._of_kind = {kind: [r for r in rules if r["kind"] == kind] for kind in APPLIED_KINDS}

    def payer(self, txn: dict) -> tuple[str, dict] | None:
        """The party a rule says this line pays for, if any."""
        text = normalize(f"{txn.get('text') or ''} {txn.get('counterparty_name') or ''}")
        for rule in self._of_kind["payer_is_customer"]:
            params = rule["params"]
            if not _in_scope(rule, txn["entity"]):
                continue
            by_iban = params.get("iban") and params["iban"] == txn.get("counterparty_account")
            by_name = params.get("payerName") and normalize(params["payerName"]) in text
            if by_iban or by_name:
                return params["partyId"], rule
        return None

    def paid_for(self, parties: list[str], entity: str) -> tuple[str, dict] | None:
        for rule in self._of_kind["parent_pays"]:
            if _in_scope(rule, entity) and rule["params"]["payerPartyId"] in parties:
                return rule["params"]["forPartyId"], rule
        return None

    def alias(self, txn: dict) -> tuple[dict, dict] | None:
        text = f"{txn.get('text') or ''} {txn.get('remittance_info') or ''}".upper()
        for rule in self._of_kind["reference_alias"]:
            if _in_scope(rule, txn["entity"]) and rule["params"]["pattern"].upper() in text:
                return rule["params"], rule
        return None

    def categories(self, phase) -> dict[str, Proposal]:
        rules = self._of_kind["always_category"]
        if not rules:
            return {}
        columns = ("bank_txn_id", "entity", "bank", "bank_code", "bank_subcode", "text")
        out = {}
        for txn in phase.txns.select(columns).iter_rows(named=True):
            for rule in rules:
                if _in_scope(rule, txn["entity"]) and _category_matches(rule["params"], txn):
                    out[txn["bank_txn_id"]] = Proposal(rule=RULE, lines=[], category=rule["params"]["category"],
                                                       sources=evidence(rule))
                    break
        return out


def _category_matches(params: dict, txn: dict) -> bool:
    fields = (("bank", "bank"), ("bankCode", "bank_code"), ("bankSubcode", "bank_subcode"))
    if any(params.get(key) and params[key] != txn[column] for key, column in fields):
        return False
    pattern = params.get("textPattern")
    return not pattern or re.search(pattern, txn["text"] or "") is not None

"""CONTRACT §4: what a person teaches applies in the next run, with priority and its evidence."""
from __future__ import annotations

import gzip
import json
from types import SimpleNamespace

import polars as pl
from test_party_amount import NAME, engine, item, lines, txn

from closebooks.api.jobs import with_memory
from closebooks.memory import Memory, load_rules
from closebooks.pipeline import run_pipeline


def _write(folder, *rules):
    folder.mkdir(exist_ok=True)
    (folder / "memory_rules.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rules))
    return folder


def _rule(rule_id, kind, params, **extra):
    return {"ruleId": rule_id, "kind": kind, "params": params, "active": True, **extra}


def test_last_record_of_a_rule_wins_and_inactive_rules_do_not_apply(tmp_path):
    folder = _write(tmp_path, _rule("MR-1", "payer_is_customer", {"payerName": "A", "partyId": "C1"}),
                    _rule("MR-2", "payer_is_customer", {"payerName": "B", "partyId": "C2"}),
                    {**_rule("MR-1", "payer_is_customer", {}), "active": False})
    assert [r["ruleId"] for r in load_rules(folder)] == ["MR-2"]


def test_no_folder_or_file_means_no_rules(tmp_path):
    assert load_rules(tmp_path / "none") == []
    assert load_rules(None) == []


def _taught(rules, items, customers=None):
    rule, balances = engine(items) if customers is None else engine(items, customers)
    rule.memory = Memory(rules)
    return rule, balances


def test_unknown_payer_taught_as_a_customer_settles_its_invoice_with_the_rule_as_evidence():
    rules = [_rule("MR-1", "payer_is_customer", {"payerName": "Maria Vicente Rubio", "partyId": "C1"})]
    rule, balances = _taught(rules, [item("ARI-1", "C1", "FV1234", 12697)])
    moved = txn(12697, "TRANSFERENCIA DE MARIA VICENTE RUBIO")
    assert rule(moved, balances) is not None
    proposal = rule(moved, balances)
    assert lines(proposal) == {"ARI-1"}
    assert proposal.rule == "MEMORY-RULE"
    assert proposal.sources == [{"kind": "memoryRule", "ref": "MR-1"}]
    assert proposal.confidence == 1.0


def test_payer_taught_by_iban():
    rules = [_rule("MR-1", "payer_is_customer", {"iban": "ES99", "partyId": "C1"})]
    rule, balances = _taught(rules, [item("ARI-1", "C1", "FV1234", 500)])
    assert rule(txn(500, "PAGO", iban="ES99"), balances).rule == "MEMORY-RULE"


def test_rule_scoped_to_another_entity_does_not_apply():
    rules = [_rule("MR-1", "payer_is_customer", {"payerName": "Maria", "partyId": "C1"}, scope={"entity": "E9"})]
    rule, balances = _taught(rules, [item("ARI-1", "C1", "FV1234", 500)])
    assert rule(txn(500, "DE MARIA"), balances) is None


def test_taught_payer_still_needs_the_amount_to_be_explained():
    rules = [_rule("MR-1", "payer_is_customer", {"payerName": "Maria", "partyId": "C1"})]
    rule, balances = _taught(rules, [item("ARI-1", "C1", "FV1234", 500)])
    assert rule(txn(777, "DE MARIA"), balances) is None


def test_parent_pays_settles_the_invoice_of_the_child():
    rules = [_rule("MR-1", "parent_pays", {"payerPartyId": "C1", "forPartyId": "C2"})]
    customers = (("C1", "E1", "Wellness Garrido S.L.", None, None, None, None, None),
                 ("C2", "E1", "Hija S.L.", None, None, None, None, None))
    rule, balances = _taught(rules, [item("ARI-2", "C2", "FV9999", 800)], customers)
    assert lines(rule(txn(800, NAME), balances)) == {"ARI-2"}


def test_reference_alias_points_a_pattern_to_a_document():
    rules = [_rule("MR-1", "reference_alias", {"pattern": "PEDIDO-77", "documentNumber": "FV1234"})]
    rule, balances = _taught(rules, [item("ARI-1", "C1", "FV1234", 500)])
    proposal = rule(txn(500, "PAGO PEDIDO-77"), balances)
    assert lines(proposal) == {"ARI-1"}
    assert proposal.rule == "MEMORY-RULE"


def test_always_category_claims_matching_lines():
    rules = [_rule("MR-1", "always_category", {"bank": "PENA", "textPattern": "^CUOTA", "category": "LEASING"})]
    memory = Memory(rules)
    txns = pl.DataFrame({"bank_txn_id": ["A", "B", "C"], "entity": ["E1"] * 3, "bank": ["PENA", "OTRO", "PENA"],
                         "bank_code": ["1"] * 3, "bank_subcode": ["2"] * 3, "text": ["CUOTA X", "CUOTA Y", "OTRA"]})
    proposals = memory.categories(SimpleNamespace(txns=txns))
    assert list(proposals) == ["A"]
    assert proposals["A"].category == "LEASING"
    assert proposals["A"].rule == "MEMORY-RULE"


def test_rule_kinds_not_applied_are_reported_not_silently_lost():
    memory = Memory([_rule("MR-1", "ignore_suffix", {"partyId": "C1", "regex": "X"})])
    assert memory.ignored == ["MR-1"]


def test_a_rule_taught_on_a_run_changes_the_next_run_and_counts_as_applied(tmp_path, sample):
    base = run_pipeline("sample", out=tmp_path / "base", score=False)
    expl = [json.loads(line) for line in gzip.open(base / "explanations.jsonl.gz", "rt")]
    target = next(e for e in expl if e["rule"] == "FALLBACK-UNIDENTIFIED")
    text = sample.txns.filter(pl.col("bank_txn_id") == target["bankTxnId"])["text"][0]
    import re

    human = _write(tmp_path / "human", _rule("MR-1", "always_category", {
        "textPattern": "^" + re.escape(text) + "$", "category": "CUSTOMER_ADVANCE"}))
    after = run_pipeline("sample", out=tmp_path / "after", score=False, memory=human)
    rows = [json.loads(line) for line in gzip.open(after / "explanations.jsonl.gz", "rt")]
    changed = next(e for e in rows if e["bankTxnId"] == target["bankTxnId"])
    assert (changed["category"], changed["rule"]) == ("CUSTOMER_ADVANCE", "MEMORY-RULE")
    assert changed["sources"] == [{"kind": "memoryRule", "ref": "MR-1"}]
    meta = json.loads((after / "run.json").read_text())
    assert meta["memoryRulesApplied"] >= 1
    assert not (after / "human").exists()


def test_a_run_started_with_memory_from_applies_the_copied_rules(tmp_path):
    out = tmp_path / "run"
    assert with_memory(["closebooks", "run"], out) == ["closebooks", "run"]
    (out / "human").mkdir(parents=True)
    (out / "human" / "memory_rules.jsonl").write_text("")
    assert with_memory(["closebooks", "run"], out) == ["closebooks", "run", "--memory", str(out / "human")]

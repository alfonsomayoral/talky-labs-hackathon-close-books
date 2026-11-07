"""CLAUDE.md §5: every row carries its evidence. What the invoice's PDF decided has to name that PDF."""
from __future__ import annotations

from test_party_amount import NAME, engine, item, txn


def test_a_payment_the_pdf_expects_cites_that_pdf():
    rule, balances = engine([item("ARI-1", "C1", "F1", 30000), item("ARI-2", "C1", "F2", 50000)])
    rule.clauses = {"ARI-2": {"instalments": {"amounts": [20000, 15000, 15000]}, "_pdf": {"path": "pdfs/E1/F2.pdf"}}}
    found = rule(txn(15000, NAME), balances)
    assert found.rule == "PARTY-PLAN"
    assert {"kind": "pdf", "ref": "pdfs/E1/F2.pdf"} in found.sources

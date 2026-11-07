"""R6: CAT-CODE and CAT-TEXT. A line that settles no item, when the evidence is strong (POLICIES §4)."""
from __future__ import annotations

import polars as pl

from ..categories import Codes, load_codes, pure_category, text_category
from ..load import Phase
from ..model import Proposal
from .parties import normalize

NAME_PREFIX = 8  # characters of the supplier name that identify it in a truncated bank text


def claim(txn: dict, codes: Codes) -> Proposal | None:
    """The code decides when its history is pure; otherwise only an unmistakable keyword does."""
    category, rule = pure_category(codes, txn), "CAT-CODE"
    if category is None:
        category, rule = text_category(txn), "CAT-TEXT"
    if category is None and text_category({**txn, "text": txn.get("remittance_info")}) == "SUPPLIER_REFUND":
        category, rule = "SUPPLIER_REFUND", "CAT-TEXT"  # "ABONO PAGO DOBLE" travels in the remittance field
    if category is None:
        return None
    label = f"{txn['bank']} {txn['bank_code'] or ''}/{txn['bank_subcode'] or ''}"
    return Proposal(rule=rule, lines=[], category=category,
                    sources=[{"kind": "bankLine", "ref": txn["bank_txn_id"], "label": label}])


def _norm(text: str | None) -> str:
    return normalize(text).replace(" ", "")


def propose_supplier_refunds(phase: Phase) -> dict[str, Proposal]:
    """CAT-SUPPLIER-REFUND (POLICIES §4): a receipt of the exact amount of one of our supplier's credit notes, citing
    its number or the supplier, settles that credit note. Two candidates with the same evidence are not guessed."""
    names = phase.masters["suppliers"].select(
        pl.col("supplier_id").alias("party_id"), pl.col("name").alias("master_name")).unique("party_id")
    notes = phase.items.filter(pl.col("item_type") == "APC").join(names, on="party_id", how="left").select(
        "item_id", "entity", "party_id", "document_number", "related_document", "currency", "total_cents", "issue_date",
        pl.coalesce("party_name", "master_name").alias("name"))
    credits = phase.txns.filter(pl.col("amount_cents") > 0).select(
        "bank_txn_id", "entity", "currency", "amount_cents", "booking_date",
        pl.concat_str(["text", "ref1", "ref2", "end_to_end_id", "remittance_info", "counterparty_name"], separator=" ",
                      ignore_nulls=True).alias("all_text"))
    pairs = credits.join(notes, left_on=["entity", "currency", "amount_cents"],
                         right_on=["entity", "currency", "total_cents"]).filter(
        pl.col("issue_date") <= pl.col("booking_date"))
    evidence = []
    for pair in pairs.iter_rows(named=True):
        text = _norm(pair["all_text"])
        number = next((n for n in (pair["document_number"], pair["related_document"])
                       if len(_norm(n)) >= 4 and _norm(n) in text), None)
        name = _norm(pair["name"])[:NAME_PREFIX]
        if number or (len(name) >= 5 and name in text):
            evidence.append({**pair, "reference": number})
    found = pl.DataFrame(evidence, schema=pairs.schema | {"reference": pl.String}) if evidence else None
    if found is None:
        return {}
    # One candidate per receipt; a credit note refunded twice stays with the first receipt.
    found = found.filter(pl.len().over("bank_txn_id") == 1).sort("booking_date", "bank_txn_id").unique(
        "item_id", keep="first")
    return {
        r["bank_txn_id"]: Proposal(
            rule="CAT-SUPPLIER-REFUND", lines=[(r["item_id"], None)], party_id=r["party_id"], reference=r["reference"],
            sources=[{"kind": "supplier", "ref": r["party_id"]}])
        for r in found.iter_rows(named=True)
    }


def propose(phase: Phase) -> dict[str, Proposal]:
    proposals = propose_supplier_refunds(phase)
    codes = load_codes()
    for txn in phase.txns.select("bank_txn_id", "bank", "bank_code", "bank_subcode", "amount_cents", "text",
                                  "remittance_info").iter_rows(
            named=True):
        proposal = claim(txn, codes)
        if proposal:
            proposals.setdefault(txn["bank_txn_id"], proposal)
    return proposals

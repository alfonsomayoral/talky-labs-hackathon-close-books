"""Cases: what the platform shows and a person decides (CONTRACT §2.2)."""
from __future__ import annotations

from .model import Row

CLOSED_RULE_FAMILIES = ("FILE-", "REF-", "ADVICE-")


def _priority(amount_eur: int) -> int:
    if abs(amount_eur) >= 10_000_000:
        return 1
    return 2 if abs(amount_eur) >= 500_000 else 3


def _money(cents: int, currency: str) -> str:
    text = f"{abs(cents) / 100:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{text} {currency}"


def _classify(row: Row, txn: dict) -> tuple[str, str, str]:
    """kind, status, suggestedAction."""
    if row.rule == "FALLBACK-UNIDENTIFIED":
        return "unidentified_receipt", "fallback", "review"
    if row.rule.startswith("FALLBACK-"):
        return "unknown_debit", "fallback", "review"
    return "ambiguous_match", "needs_review" if row.confidence < 0.9 else "auto", "review"


def build_cases(rows: list[Row], txns: dict[str, dict], created_at: str) -> list[dict]:
    """One case per bank line not closed with confidence 1 by a file, advice or reference rule."""
    cases = []
    seen: set[str] = set()
    for row in rows:
        txn_id = row.bank_txn_id
        if txn_id in seen or (row.confidence >= 1.0 and row.rule.startswith(CLOSED_RULE_FAMILIES)):
            continue
        seen.add(txn_id)
        txn = txns[txn_id]
        kind, status, action = _classify(row, txn)
        who = txn["counterparty_name"] or (txn["text"] or "")[:60]
        cases.append({
            "caseId": f"CASE-{txn_id}", "kind": kind, "status": status, "priority": _priority(txn["amount_eur_cents"]),
            "entity": txn["entity"], "bankTxnId": txn_id, "partyId": row.party_id,
            "itemIds": [r for r in [row.item_id] if r], "amountCents": txn["amount_cents"],
            "currency": txn["currency"], "amountEur": txn["amount_eur_cents"], "bookingDate": txn["booking_date"],
            "summary": f"{'Cobro' if txn['amount_cents'] > 0 else 'Cargo'} de "
                       f"{_money(txn['amount_cents'], txn['currency'])} sin casación: {who}",
            "suggestedAction": action, "questionId": None, "draftId": None, "rule": row.rule,
            "createdAt": created_at,
        })
    return cases

"""Cases: what the platform shows and a person decides (CONTRACT §2.2)."""
from __future__ import annotations

from .model import Row

CLOSED_RULE_FAMILIES = ("FILE-", "REF-", "ADVICE-", "CAT-")
_SUPPLIER_ISSUE_TEXT = {"PARTIAL": "pagada en parte", "RETURNED": "devuelta por el banco",
                        "DUPLICATE_PAYMENT": "pagada dos veces"}
SUPPLIER_ISSUES = tuple(_SUPPLIER_ISSUE_TEXT)
_EXCEPTION_ORDER = ("RETURNED", "DUPLICATE_PAYMENT", "SHORT_DISPUTE", "OVERPAYMENT", "PARTIAL", "FX_DIFFERENCE")
_CUSTOMER_KINDS = {
    "PARTIAL": ("short_payment", "review"),
    "RETURNED": ("returned", "email_customer"),
    "DUPLICATE_PAYMENT": ("duplicate_payment", "email_customer"),
    "SHORT_DISPUTE": ("dispute", "email_customer"),
    "OVERPAYMENT": ("overpayment", "email_customer"),
}


def _priority(amount_eur: int) -> int:
    if abs(amount_eur) >= 10_000_000:
        return 1
    return 2 if abs(amount_eur) >= 500_000 else 3


def _money(cents: int, currency: str) -> str:
    text = f"{abs(cents) / 100:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{text} {currency}"


def _classify(row: Row, exception: str | None) -> tuple[str, str]:
    """kind and suggestedAction of a bank line, from the most telling of its exceptions."""
    if row.rule == "FALLBACK-UNIDENTIFIED":
        return "unidentified_receipt", "review"
    if row.rule.startswith("FALLBACK-"):
        return "unknown_debit", "review"
    if exception == "FX_DIFFERENCE":
        return "fx_difference", "none"
    if exception in _CUSTOMER_KINDS:
        return _CUSTOMER_KINDS[exception]
    return "ambiguous_match", "review"


def _status(row: Row) -> str:
    if row.rule.startswith("FALLBACK-"):
        return "fallback"
    return "needs_review" if row.confidence < 0.9 else "auto"


def _supplier_cases(issues: list[Row], lines: list[Row], txn: dict, created_at: str) -> list[dict]:
    """One case per supplier invoice with an incident: a bulk payment cannot be written about as a single supplier."""
    paid = sum(r.amount_cents for r in lines) or 1
    cases = []
    for row in issues:
        eur = round(abs(txn["amount_eur_cents"]) * row.amount_cents / paid)
        cases.append({
            "caseId": f"CASE-{txn['bank_txn_id']}-{row.item_id}", "kind": "supplier_invoice_mismatch",
            "status": _status(row), "priority": _priority(eur), "entity": txn["entity"],
            "bankTxnId": txn["bank_txn_id"], "partyId": row.party_id, "itemIds": [row.item_id],
            "amountCents": row.amount_cents, "currency": row.currency, "amountEur": eur,
            "bookingDate": txn["booking_date"],
            "summary": f"Factura de proveedor {_SUPPLIER_ISSUE_TEXT[row.exception]}: "
                       f"{_money(row.amount_cents, row.currency)}",
            "suggestedAction": "email_supplier", "questionId": None, "draftId": None, "rule": row.rule,
            "createdAt": created_at,
        })
    return cases


def build_cases(rows: list[Row], txns: dict[str, dict], created_at: str) -> list[dict]:
    """One case per bank line not closed cleanly: an exception, a fallback or less than full confidence."""
    by_txn: dict[str, list[Row]] = {}
    for row in rows:
        by_txn.setdefault(row.bank_txn_id, []).append(row)
    cases = []
    for txn_id, lines in by_txn.items():
        txn = txns[txn_id]
        issues = [r for r in lines if r.item_id and r.item_id[:2] == "AP" and r.exception in SUPPLIER_ISSUES]
        if issues:
            cases += _supplier_cases(issues, lines, txn, created_at)
            lines = [r for r in lines if r not in issues] if len(issues) < len(lines) else []
            if not any(r.exception for r in lines):
                continue
        if not lines:
            continue
        exceptions = {r.exception for r in lines if r.exception}
        first = min(lines, key=lambda r: r.confidence)
        clean = first.confidence >= 1.0 and first.rule.startswith(CLOSED_RULE_FAMILIES)
        if clean and not exceptions:
            continue
        exception = next((e for e in _EXCEPTION_ORDER if e in exceptions), None)
        kind, action = _classify(first, exception)
        who = txn["counterparty_name"] or (txn["text"] or "")[:60]
        verb = "Cobro" if txn["amount_cents"] > 0 else "Cargo"
        tail = exception or "sin casación"
        cases.append({
            "caseId": f"CASE-{txn_id}", "kind": kind, "status": _status(first),
            "priority": _priority(txn["amount_eur_cents"]), "entity": txn["entity"], "bankTxnId": txn_id,
            "partyId": first.party_id, "itemIds": [r.item_id for r in lines if r.item_id],
            "amountCents": abs(txn["amount_cents"]), "currency": txn["currency"],
            "amountEur": abs(txn["amount_eur_cents"]), "bookingDate": txn["booking_date"],
            "summary": f"{verb} de {_money(txn['amount_cents'], txn['currency'])} ({tail}): {who}",
            "suggestedAction": action, "questionId": None, "draftId": None, "rule": first.rule,
            "createdAt": created_at,
        })
    return cases

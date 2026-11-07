"""Cases: what the platform shows and a person decides (CONTRACT §2.2)."""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from .model import Row

CLOSED_RULE_FAMILIES = ("FILE-", "REF-", "ADVICE-", "CAT-", "MEMORY-")
_SUPPLIER_ISSUE_TEXT = {"PARTIAL": "pagada en parte", "RETURNED": "devuelta por el banco",
                        "DUPLICATE_PAYMENT": "pagada dos veces"}
SUPPLIER_ISSUES = tuple(_SUPPLIER_ISSUE_TEXT)
_CUSTOMER_ISSUE_TEXT = {"SHORT_DISPUTE": "con una parte disputada", "PARTIAL": "pagada en parte"}
OVERDUE_MIN_DAYS = 15
RECENT_MOVEMENT_DAYS = 30
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


REVIEW_KINDS = ("dispute", "short_payment")  # the platform cannot tell by itself whether the deduction is right
MAX_OVERDUE_PER_ENTITY = 500
MAX_QUESTIONS = 500
_RULE_TEXT = (
    ("FILE-PAYMENT-RUN", "por fichero de pagos"), ("FILE-PAYMENT-RETURN", "por devolución de pago"),
    ("FILE-DD-BATCH", "por remesa de adeudos"), ("FILE-DD-RETURN", "por devolución de adeudo"),
    ("FILE-CARD-CHARGEBACK", "por contracargo de tarjeta"), ("FILE-CARD", "por liquidación de tarjetas"),
    ("FILE-CHEQUE-RETURN", "por cheque devuelto"), ("FILE-CHEQUE", "por ingreso de cheques"),
    ("ADVICE-", "por aviso de remesa"), ("REF-", "por la referencia del movimiento"),
    ("PARTY-SUBSET", "por tercero y suma de facturas"), ("PARTY-SHORT", "por tercero e importe con deducción"),
    ("PARTY-", "por tercero e importe"), ("MEMORY-RULE", "por una regla guardada"),
)
_EXCEPTION_TEXT = {
    "SHORT_DISPUTE": ("con disputa", "con disputa"), "PARTIAL": ("pagada en parte", "pagadas en parte"),
    "RETURNED": ("devuelta", "devueltas"), "DUPLICATE_PAYMENT": ("pagada dos veces", "pagadas dos veces"),
    "OVERPAYMENT": ("con sobrepago", "con sobrepago"), "FX_DIFFERENCE": ("con diferencia de cambio",
                                                                         "con diferencia de cambio"),
}


def _status(row: Row, kind: str = "") -> str:
    if row.rule.startswith("FALLBACK-"):
        return "fallback"
    return "needs_review" if row.confidence < 0.9 or kind in REVIEW_KINDS else "auto"


def _count(n: int) -> str:
    return "una" if n == 1 else str(n)


def _settled_text(lines: list[Row], rule: str) -> str:
    """'886 facturas liquidadas por aviso de remesa, una con disputa': what the line did, with no rule codes."""
    settled = sum(1 for r in lines if r.item_id)
    how = next((text for prefix, text in _RULE_TEXT if rule.startswith(prefix)), "")
    text = f"{_count(settled)} {'factura liquidada' if settled == 1 else 'facturas liquidadas'} {how}".rstrip()
    for exception, (one, many) in _EXCEPTION_TEXT.items():
        n = sum(1 for r in lines if r.exception == exception)
        if n:
            text += f", {_count(n)} {one if n == 1 else many}"
    return text


def _customer_cases(issues: list[Row], lines: list[Row], txn: dict, created_at: str) -> list[dict]:
    """One case per customer invoice disputed or left short: a remittance of 886 invoices has one thing to review."""
    paid = sum(r.amount_cents for r in lines) or 1
    cases = []
    for row in issues:
        eur = round(abs(txn["amount_eur_cents"]) * row.amount_cents / paid)
        kind, action = _CUSTOMER_KINDS[row.exception]
        cases.append({
            "caseId": f"CASE-{txn['bank_txn_id']}-{row.item_id}", "kind": kind, "status": "needs_review",
            "priority": _priority(eur), "entity": txn["entity"], "bankTxnId": txn["bank_txn_id"],
            "partyId": row.party_id, "itemIds": [row.item_id], "amountCents": row.amount_cents,
            "currency": row.currency, "amountEur": eur, "bookingDate": txn["booking_date"],
            "summary": f"Factura {_CUSTOMER_ISSUE_TEXT[row.exception]}: {_money(row.amount_cents, row.currency)}",
            "suggestedAction": action, "questionId": None, "draftId": None, "rule": row.rule,
            "createdAt": created_at,
        })
    return cases


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
        customer_issues = [r for r in lines
                           if r.item_id and r.item_id[:2] == "AR" and r.exception in _CUSTOMER_ISSUE_TEXT]
        if customer_issues:
            all_lines = by_txn[txn_id]
            cases += _customer_cases(customer_issues, all_lines, txn, created_at)
            lines = [r for r in lines if r not in customer_issues]
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
        tail = (exception or "sin casación") if first.rule.startswith("FALLBACK-") else _settled_text(lines, first.rule)
        cases.append({
            "caseId": f"CASE-{txn_id}", "kind": kind, "status": _status(first, kind),
            "priority": _priority(txn["amount_eur_cents"]), "entity": txn["entity"], "bankTxnId": txn_id,
            "partyId": first.party_id, "itemIds": [r.item_id for r in lines if r.item_id],
            "amountCents": abs(txn["amount_cents"]), "currency": txn["currency"],
            "amountEur": abs(txn["amount_eur_cents"]), "bookingDate": txn["booking_date"],
            "summary": f"{verb} de {_money(txn['amount_cents'], txn['currency'])} ({who}): {tail}",
            "suggestedAction": action, "questionId": None, "draftId": None, "rule": first.rule,
            "createdAt": created_at,
        })
    return cases


def overdue_cases(items: list[dict], cutoff: str, rates: dict[str, float], names: dict[str, str],
                  created_at: str, last_movement: dict[str, str]) -> list[dict]:
    """One case per customer with balance more than 15 days past due at the end of the phase and no movement in the
    last 30 days: a customer who pays and whom we do not match is our problem, not a debt.

    `items`: customer invoices with their final balance (item_id, entity, party_id, due_date, currency,
    open_cents). Cutoff is the last booking date; rates are units per EUR at that date."""
    end = date.fromisoformat(cutoff)
    due_before = (end - timedelta(days=OVERDUE_MIN_DAYS)).isoformat()
    moved_since = (end - timedelta(days=RECENT_MOVEMENT_DAYS)).isoformat()
    by_party: dict[tuple[str, str], list[dict]] = {}
    for item in items:
        if last_movement.get(item["party_id"], "") >= moved_since:
            continue
        if item["open_cents"] > 0 and item["due_date"] and item["due_date"] < due_before:
            by_party.setdefault((item["entity"], item["party_id"]), []).append(item)
    totals = []
    for (entity, party), group in by_party.items():
        eur = sum(round(i["open_cents"] / rates.get(i["currency"], 1.0)) for i in group)
        totals.append((entity, party, eur, group))
    kept = []
    for entity in {t[0] for t in totals}:
        kept += sorted((t for t in totals if t[0] == entity), key=lambda t: (-t[2], t[1]))[:MAX_OVERDUE_PER_ENTITY]
    cases = []
    for n, (entity, party, eur, group) in enumerate(sorted(kept, key=lambda t: (-t[2], t[0], t[1])), 1):
        group.sort(key=lambda i: (i["due_date"], i["item_id"]))
        count = len(group)
        cases.append({
            "caseId": f"CASE-overdue_customer-{n}", "kind": "overdue_customer", "status": "needs_review",
            "priority": _priority(eur), "entity": entity, "bankTxnId": None, "partyId": party,
            "itemIds": [i["item_id"] for i in group], "amountCents": eur, "currency": "EUR", "amountEur": eur,
            "bookingDate": cutoff,
            "summary": f"{names.get(party, party)}: {_count(count)} "
                       f"{'factura vencida' if count == 1 else 'facturas vencidas'} por {_money(eur, 'EUR')}, "
                       f"la más antigua desde el {group[0]['due_date']}",
            "suggestedAction": "email_customer", "questionId": None, "draftId": None, "rule": "OVERDUE-BALANCE",
            "createdAt": created_at,
        })
    return cases


def _item_label(item: dict, open_cents: int, currency: str) -> str:
    due = f" · vence {item['due_date']}" if item.get("due_date") else ""
    return f"{item['number']} · {_money(open_cents, currency)} · {item['party_name']}{due}"


def _option(option: dict, info: dict[str, dict], names: dict[str, str]) -> dict:
    ids = [i for i, _ in option["items"]]
    cents = sum(-o if i[:3] in ("ARC", "APC") else o for i, o in option["items"])  # credit notes net off
    currency = info[ids[0]]["currency"]
    if option["kind"] == "party":
        numbers = ", ".join(info[i]["number"] for i in ids[:3]) + (f" y {len(ids) - 3} más" if len(ids) > 3 else "")
        return {"id": option["partyId"], "label": f"{names.get(option['partyId'], option['partyId'])} · {numbers} · "
                                                  f"{_money(cents, currency)}"}
    if len(ids) == 1:
        return {"id": ids[0], "label": _item_label(info[ids[0]], cents, currency)}
    numbers = " + ".join(info[i]["number"] for i in ids)
    party = names.get(option["partyId"]) or info[ids[0]]["party_name"] or option["partyId"]
    return {"id": "+".join(ids), "label": f"{numbers} · {_money(cents, currency)} · {party}"}


def attach_questions(cases: list[dict], abstentions: dict[str, dict], txns: dict[str, dict], info_of: Callable,
                     names: dict[str, str], created_at: str) -> list[dict]:
    """A question per abstention (the biggest MAX_QUESTIONS): the cases turn into `question` cases, in place."""
    by_id = {c["caseId"]: c for c in cases}
    ranked = sorted((t for t in abstentions if f"CASE-{t}" in by_id and t in txns),
                    key=lambda t: (-abs(txns[t]["amount_eur_cents"]), t))[:MAX_QUESTIONS]
    info = info_of([i for t in ranked for o in abstentions[t]["options"] for i, _ in o["items"]])
    questions = []
    for n, txn_id in enumerate(ranked, 1):
        txn, abstention, case = txns[txn_id], abstentions[txn_id], by_id[f"CASE-{txn_id}"]
        by_party = abstention["reason"] == "parties"
        options = sorted((_option({**o, "kind": "party" if by_party else "items"}, info, names)
                          for o in abstention["options"]), key=lambda o: o["id"])
        incoming = txn["amount_cents"] > 0
        payer = txn["counterparty_name"]
        cash = _money(abs(txn["amount_cents"]), txn["currency"])
        what = f"{'este cobro' if incoming else 'este cargo'} de {cash}" + (f" de {payer}" if payer else "")
        if by_party:
            ask = f"¿De qué {'cliente' if incoming else 'proveedor'} es {what}?"
        else:
            ask = f"¿Qué facturas liquida {what}?"
        # the rule keys on the counterparty's name, or its account when the line has no name; with neither there is
        # nothing to remember and the preview is null
        key = ({"payerName": payer} if payer else {"iban": txn.get("counterparty_account")}
               if txn.get("counterparty_account") else None)
        preview = None
        if key:
            who = payer or txn["counterparty_account"]
            what_party = "cliente" if incoming else "proveedor"
            preview = {"kind": "payer_is_customer", **key, "partyId": "<la opción elegida>",
                       "description": f"En adelante, los {'cobros de' if incoming else 'pagos a'} {who} se asignan "
                                      f"al {what_party} elegido"}
        question_id = f"Q-{n:06d}"
        questions.append({
            "questionId": question_id, "caseId": case["caseId"], "bankTxnId": txn_id, "entity": txn["entity"],
            "question": ask, "options": [*options, {"id": "none", "label": "Ninguna: dejar sin identificar"}],
            "defaultOption": "none", "rulePreview": preview, "status": "open", "createdAt": created_at})
        case.update(kind="ambiguous_match", status="question", suggestedAction="ask", questionId=question_id,
                    summary=f"{case['summary']}. Hay {len(options)} opciones con la misma evidencia")
    return questions

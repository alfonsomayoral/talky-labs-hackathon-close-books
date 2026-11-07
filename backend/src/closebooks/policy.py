"""Amount and exception of each row (POLICIES §2-§3), in one place whichever rule produced the match."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

CREDIT_NOTES = ("ARC", "APC")
GRACE_DAYS = 3
WITHHOLDING_RATES = (0.0125, 0.015, 0.10)
WITHHOLDING_COUNTRIES = ("MX", "BR", "MA")  # POLICIES §3
# Where a shortfall is an intermediary's fee: outside SEPA (POLICIES §3). The fee is checked apart from the country.
SEPA_COUNTRIES = frozenset(
    "AT BE BG CY CZ DE DK EE ES FI FR GR HR HU IE IS IT LI LT LU LV NL NO PT RO SE SI SK AD MC SM VA".split())
MAX_OVERPAYMENT_RATIO = 0.35  # above this the text cited only part of what the cash pays
CROSS_BORDER_MARKS = ("EN DIV", "GASTOS SHA", "GASTOS BEN")
FEE_LIMIT_EUR_CENTS = 6000
FEE_LIMIT_RATIO = 0.02
DISCOUNT_WORDS = ("DISCOUNT", "DESCUENTO", "DTO", "SKONTO", "ESCOMPTE", "SCONTO")
WITHHOLDING_WORDS = ("RET", "RETENCION", "RETENCIÓN", "WITHHOLDING", "WHT", "ISR", "IRRF")


def cross_border(bank_code: str | None, text: str | None) -> bool:
    """The bank says it came from abroad: only then can a small shortfall be an intermediary's fee."""
    upper = (text or "").upper()
    return "XBCT" in (bank_code or "") or any(mark in upper for mark in CROSS_BORDER_MARKS)


@dataclass(slots=True)
class Terms:
    discount_pct: float | None
    discount_days: int | None
    issue_date: str | None
    total_cents: int
    country: str | None = None


def _in_terms(terms: Terms | None, booking_date: str | None) -> bool:
    if terms is None or not terms.discount_pct or terms.discount_days is None:
        return False
    if not terms.issue_date or not booking_date:
        return False
    deadline = date.fromisoformat(terms.issue_date) + timedelta(days=terms.discount_days + GRACE_DAYS)
    return date.fromisoformat(booking_date) <= deadline


def _discount_cents(terms: Terms | None) -> int | None:
    if terms is None or not terms.discount_pct:
        return None
    return round(terms.total_cents * terms.discount_pct / 100)


def _is_rate(shortfall: int, total: int, rate: float) -> bool:
    return abs(shortfall - round(total * rate)) <= 1


def _deducted(open_cents: int, applied: int, deduction: tuple[int, str | None], terms: Terms | None,
              booking_date: str | None) -> tuple[int, str]:
    """A document prints what was deducted and, usually, why."""
    shortfall, reason = abs(deduction[0]), (deduction[1] or "").strip().upper()
    if not shortfall or applied >= open_cents:
        return open_cents, ""
    total = terms.total_cents if terms else open_cents
    is_discount = any(word in reason for word in DISCOUNT_WORDS)
    is_withholding = any(reason == word or reason.startswith(word + " ") for word in WITHHOLDING_WORDS)
    if reason and not is_discount and not is_withholding:
        return applied, "SHORT_DISPUTE"
    discount = _discount_cents(terms)
    if not reason:
        is_withholding = any(_is_rate(shortfall, total, rate) for rate in WITHHOLDING_RATES)
        is_discount = discount is not None and abs(shortfall - discount) <= 1
    if is_withholding:
        return open_cents, "SHORT_WITHHOLDING"
    if is_discount and discount is not None and abs(shortfall - discount) <= 1 and _in_terms(terms, booking_date):
        return open_cents, "SHORT_DISCOUNT"
    return applied, "PARTIAL"


def decide(item_id: str, item_currency: str, txn_currency: str, open_cents: int, applied_cents: int | None,
           returned: bool = False, *, deduction: tuple[int, str | None] | None = None, terms: Terms | None = None,
           booking_date: str | None = None) -> tuple[int, str]:
    if returned:
        return (applied_cents if applied_cents is not None else open_cents), "RETURNED"
    if open_cents <= 0:
        amount = applied_cents if applied_cents is not None else 0
        exact = terms is None or amount == terms.total_cents
        return amount, "DUPLICATE_PAYMENT" if exact else ""
    if deduction is not None and applied_cents is not None:
        amount, exception = _deducted(open_cents, applied_cents, deduction, terms, booking_date)
    elif applied_cents is not None and applied_cents < open_cents:
        amount, exception = applied_cents, "PARTIAL"
    else:
        amount, exception = open_cents, ""
    return _with_fx(item_id, item_currency != txn_currency, amount, exception)


def _with_fx(item_id: str, foreign: bool, amount: int, exception: str) -> tuple[int, str]:
    """FX_DIFFERENCE replaces empty and the full-clearing exceptions; PARTIAL, SHORT_DISPUTE and credit notes keep."""
    if foreign and item_id[:3] not in CREDIT_NOTES and exception not in ("PARTIAL", "SHORT_DISPUTE"):
        return amount, "FX_DIFFERENCE"
    return amount, exception


def allocate(cash: int | None, items: list[tuple[str, int, Terms]], booking_date: str, foreign: bool,
             eur_per_cent: float | None = None) -> dict[str, tuple[int, str]]:
    """No document says how much goes to each item: explain the cash against the open balances.

    cash is in the items' currency; None when a foreign payment does not state it (then it clears what it cites).
    """
    invoices = [i for i in items if i[0][:3] not in CREDIT_NOTES]
    notes = [i for i in items if i[0][:3] in CREDIT_NOTES]
    out = {item: (open_cents, "") for item, open_cents, _ in notes}
    if len(items) == 1 and items[0][1] <= 0:
        return {items[0][0]: (cash or 0, "DUPLICATE_PAYMENT" if cash == items[0][2].total_cents else "")}
    net = sum(o for _, o, _ in invoices) - sum(o for _, o, _ in notes)
    if cash is None:
        cash = net
    gap = net - cash
    result = _explain(gap, cash, invoices, notes, booking_date, eur_per_cent)
    out.update(result)
    return {item: _with_fx(item, foreign, *value) for item, value in out.items()}


def _explain(gap: int, cash: int, invoices: list, notes: list, booking_date: str,
             eur_per_cent: float | None) -> dict[str, tuple[int, str]]:
    clear = {item: (open_cents, "") for item, open_cents, _ in invoices}
    if gap == 0 or not invoices:
        return clear
    if gap < 0:
        if len(invoices) == 1 and not notes and -gap <= invoices[0][1] * MAX_OVERPAYMENT_RATIO:
            return {invoices[0][0]: (invoices[0][1], "OVERPAYMENT")}
        return clear
    full = [(i, o, t) for i, o, t in invoices if o == t.total_cents]
    discounts = {i: _discount_cents(t) for i, _, t in full}
    if len(full) == len(invoices) and all(discounts.values()) and abs(sum(discounts.values()) - gap) <= len(full):
        return {i: (o, "SHORT_DISCOUNT") if _in_terms(t, booking_date) else (o - discounts[i], "PARTIAL")
                for i, o, t in invoices}
    if len(full) == len(invoices) and all(t.country in WITHHOLDING_COUNTRIES for _, _, t in invoices):
        for rate in WITHHOLDING_RATES:
            if abs(sum(round(t.total_cents * rate) for _, _, t in invoices) - gap) <= len(invoices):
                return {i: (o, "SHORT_WITHHOLDING") for i, o, _ in invoices}
    if len(invoices) == 1 and eur_per_cent is not None:
        item, open_cents, terms = invoices[0]
        fee_ok = gap * eur_per_cent <= FEE_LIMIT_EUR_CENTS and gap <= open_cents * FEE_LIMIT_RATIO
        if fee_ok and terms.country and terms.country not in SEPA_COUNTRIES:
            return {item: (open_cents, "SHORT_BANK_CHARGES")}
    return _oldest_first(cash + sum(o for _, o, _ in notes), invoices)


def _oldest_first(available: int, invoices: list) -> dict[str, tuple[int, str]]:
    out = {}
    for item, open_cents, _ in sorted(invoices, key=lambda i: (i[2].issue_date or "", i[0])):
        applied = min(available, open_cents)
        if applied > 0:
            out[item] = (open_cents, "") if applied == open_cents else (applied, "PARTIAL")
        available -= applied
    return out

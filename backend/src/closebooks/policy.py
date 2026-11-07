"""Amount and exception of each row (POLICIES §2-§3), in one place whichever rule produced the match."""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import IntEnum

CREDIT_NOTES = ("ARC", "APC")
GRACE_DAYS = 3
WITHHOLDING_RATES = (0.0125, 0.015, 0.10)
WITHHOLDING_COUNTRIES = ("MX", "BR", "MA")  # POLICIES §3
# Where a shortfall is an intermediary's fee: outside SEPA (POLICIES §3). The fee is checked apart from the country.
SEPA_COUNTRIES = frozenset(
    "AT BE BG CY CZ DE DK EE ES FI FR GR HR HU IE IS IT LI LT LU LV NL NO PT RO SE SI SK AD MC SM VA".split())
# Excess the golden's overpayments show. Anything else means the text cited only part of what the cash pays.
SMALL_OVERPAYMENT_RATIO = 0.02
ROUND_OVERPAYMENT_RATIO = 0.10
CROSS_BORDER_MARKS = ("EN DIV", "GASTOS SHA", "GASTOS BEN")
STATED_FEE = re.compile(r"/CHGS/([A-Z]{3})(\d+)[.,](\d{2})")
FEE_LIMIT_EUR_CENTS = 6000
FEE_LIMIT_RATIO = 0.02
DISCOUNT_WORDS = ("DISCOUNT", "DESCUENTO", "DTO", "SKONTO", "ESCOMPTE", "SCONTO")
WITHHOLDING_WORDS = ("RET", "RETENCION", "RETENCIÓN", "WITHHOLDING", "WHT", "ISR", "IRRF")
# As in rules/party_amount.py, which imports this module: a partial pays a round share, a multiple of 5 %, to the cent.
ROUND_FRACTIONS = 20
SHARE_WINDOW = 3
MAX_CHANCE = 0.05


def cross_border(bank_code: str | None, text: str | None) -> bool:
    """The bank says it came from abroad: only then can a small shortfall be an intermediary's fee."""
    upper = (text or "").upper()
    return ("XBCT" in (bank_code or "") or any(mark in upper for mark in CROSS_BORDER_MARKS)
            or STATED_FEE.search(upper) is not None)


def fee_fits(text: str | None, currency: str, shortfall: int) -> bool:
    """A fee the bank states explains the shortfall of exactly that amount and currency; with none stated, the limits.

    Why it generalizes: /CHGS/ is not a word of one bank but the movement stating the fee an intermediary took (POLICIES
    §3), whatever the transfer code, and the check is its own amount against the cash, with no cut learned from data.
    The customer's country and the 60 EUR and 2 % limits still decide, from the master and the policy."""
    stated = STATED_FEE.search((text or "").upper())
    return stated is None or (stated[1], int(stated[2]) * 100 + int(stated[3])) == (currency, shortfall)


@dataclass(slots=True)
class Terms:
    discount_pct: float | None
    discount_days: int | None
    issue_date: str | None
    total_cents: int
    country: str | None = None
    listed_at: int | None = None


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


class Evidence(IntEnum):
    """What backs a hypothesis, weakest first. Two different hypotheses on one level are a tie: neither is taken."""

    DEFAULT = 0  # nothing explains the gap: what the cash reaches
    ROUND_SHARE = 1  # with the others cleared whole, the cash pays a round share of this invoice, to the cent
    BOUNDED = 2  # within the limits POLICIES sets, not exact: an overpayment
    MOVEMENT_MARK = 3  # the bank line marks it as from abroad and the fee is within the limits of POLICIES
    RATE_ON_ALL = 4  # the rate of POLICIES on every invoice, to the rounding of each
    ONE_DISCOUNT = 5  # the gap is the discount in the terms of one invoice of several
    ALL_DISCOUNTS = 6  # the gap is the discounts in the terms of all of them
    EXACT = 7  # the open balances are the cash to the cent
    PRINTED_DISCOUNT = 8  # a document prints the amount, with no reason: it is the discount in the terms
    PRINTED_RATE = 9  # a document prints the amount, with no reason: it is a rate where that tax is withheld
    PRINTED_REASON = 10  # a document prints the amount and why


@dataclass(slots=True)
class Hypothesis:
    """One way to explain the cash: which items it settles, for how much and with which exception."""

    evidence: Evidence
    lines: dict[str, tuple[int, str]]
    why: str


def _distinct(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    """Strongest first. Two levels saying the same lines are one explanation: the stronger stays."""
    seen: dict[tuple, Hypothesis] = {}
    for hypothesis in sorted(hypotheses, key=lambda h: -h.evidence):
        seen.setdefault(tuple(sorted(hypothesis.lines.items())), hypothesis)
    return list(seen.values())


def choose(hypotheses: list[Hypothesis]) -> Hypothesis | None:
    """The strongest level with one explanation. A tie abstains on that level and leaves it to the next one down."""
    for level in sorted({h.evidence for h in hypotheses}, reverse=True):
        distinct = _distinct([h for h in hypotheses if h.evidence == level])
        if len(distinct) == 1:
            return distinct[0]
    return None


def _printed(item: str, open_cents: int, applied: int, shortfall: int, reason: str, terms: Terms | None,
             booking_date: str | None) -> Iterator[Hypothesis]:
    """What a document printed as deducted can mean."""
    def cleared(exception: str) -> dict[str, tuple[int, str]]:
        return {item: (open_cents, exception)}

    yield Hypothesis(Evidence.DEFAULT, {item: (applied, "PARTIAL")}, "the document deducts it and nothing says why")
    is_discount = any(word in reason for word in DISCOUNT_WORDS)
    is_withholding = any(reason == word or reason.startswith(word + " ") for word in WITHHOLDING_WORDS)
    if reason and not is_discount and not is_withholding:
        yield Hypothesis(Evidence.PRINTED_REASON, {item: (applied, "SHORT_DISPUTE")}, f"the document says {reason}")
        return
    discount = _discount_cents(terms)
    in_terms = discount is not None and abs(shortfall - discount) <= 1 and _in_terms(terms, booking_date)
    if is_withholding:
        yield Hypothesis(Evidence.PRINTED_REASON, cleared("SHORT_WITHHOLDING"), f"the document says {reason}")
    elif reason:
        if in_terms:
            yield Hypothesis(Evidence.PRINTED_REASON, cleared("SHORT_DISCOUNT"), f"the document says {reason}")
    else:
        total = terms.total_cents if terms else open_cents
        if (terms.country if terms else None) in (None, *WITHHOLDING_COUNTRIES) and any(
                _is_rate(shortfall, total, rate) for rate in WITHHOLDING_RATES):
            yield Hypothesis(Evidence.PRINTED_RATE, cleared("SHORT_WITHHOLDING"), "the amount printed is a tax rate")
        if in_terms:
            yield Hypothesis(Evidence.PRINTED_DISCOUNT, cleared("SHORT_DISCOUNT"), "the amount printed is the discount")


def _deducted(item: str, open_cents: int, applied: int, deduction: tuple[int, str | None], terms: Terms | None,
              booking_date: str | None) -> tuple[int, str]:
    """A document prints what was deducted and, usually, why."""
    shortfall, reason = abs(deduction[0]), (deduction[1] or "").strip().upper()
    if not shortfall or applied >= open_cents:
        return open_cents, ""
    return choose(list(_printed(item, open_cents, applied, shortfall, reason, terms, booking_date))).lines[item]


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
        amount, exception = _deducted(item_id, open_cents, applied_cents, deduction, terms, booking_date)
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
    return search(cash, items, booking_date, foreign, eur_per_cent)[0]


def search(cash: int | None, items: list[tuple[str, int, Terms]], booking_date: str, foreign: bool,
           eur_per_cent: float | None = None) -> tuple[dict[str, tuple[int, str]], list[Hypothesis]]:
    """No document says how much goes to each item: explain the cash against the open balances. Returns what each item
    takes and the different hypotheses there were, the chosen one first.

    cash is in the items' currency; None when a foreign payment does not state it (then it clears what it cites).
    """
    if len(items) == 1 and items[0][1] <= 0:
        return {items[0][0]: (cash or 0, "DUPLICATE_PAYMENT" if cash == items[0][2].total_cents else "")}, []
    invoices = [i for i in items if i[0][:3] not in CREDIT_NOTES]
    notes = [i for i in items if i[0][:3] in CREDIT_NOTES]
    net = sum(o for _, o, _ in invoices) - sum(o for _, o, _ in notes)
    if cash is None:
        cash = net
    settled_notes = {item: (open_cents, "") for item, open_cents, _ in notes}
    if not invoices:
        return _with_fx_on(settled_notes, foreign), []
    case = Gap(net - cash, cash, invoices, notes, booking_date, eur_per_cent)
    hypotheses = [hypothesis for node in NODES for hypothesis in node(case)]
    chosen = choose(hypotheses)
    considered = [chosen, *(h for h in _distinct(hypotheses) if h.lines != chosen.lines)]
    if len(considered) > 1:
        considered = [replace(h, lines=_with_fx_on(h.lines, foreign)) for h in considered]
    return _with_fx_on({**settled_notes, **chosen.lines}, foreign), considered


def _with_fx_on(lines: dict[str, tuple[int, str]], foreign: bool) -> dict[str, tuple[int, str]]:
    return {item: _with_fx(item, foreign, *value) for item, value in lines.items()}


def as_candidates(considered: list[Hypothesis], currency: str) -> list[dict]:
    """The hypotheses of a row for its evidence, one entry per item: nothing when there was only one to consider."""
    if len(considered) < 2:
        return []
    out = []
    for item in {item: None for hypothesis in considered for item in hypothesis.lines}:
        mine = [h for h in considered if item in h.lines]
        why = "; ".join(f"{'chosen ' if h is considered[0] else ''}{h.evidence.name} {h.lines[item][1] or '-'} "
                        f"{h.lines[item][0]}: {h.why}" for h in mine)
        out.append({"itemId": item, "amountCents": mine[0].lines[item][0], "currency": currency, "why": why})
    return out


@dataclass(slots=True)
class Gap:
    """What is left to explain: the open invoices less their notes, against the cash. Positive when less was paid."""

    gap: int
    cash: int
    invoices: list[tuple[str, int, Terms]]
    notes: list[tuple[str, int, Terms]]
    booking_date: str
    eur_per_cent: float | None


def _is_overpayment(excess: int, open_cents: int) -> bool:
    return excess <= open_cents * SMALL_OVERPAYMENT_RATIO or abs(excess - open_cents * ROUND_OVERPAYMENT_RATIO) <= 1


def _clear(case: Gap) -> dict[str, tuple[int, str]]:
    return {item: (open_cents, "") for item, open_cents, _ in case.invoices}


def _exact(case: Gap) -> Iterator[Hypothesis]:
    if case.gap == 0:
        yield Hypothesis(Evidence.EXACT, _clear(case), "the open balances are the cash")


def _beyond_the_balances(case: Gap) -> Iterator[Hypothesis]:
    if case.gap < 0:
        yield Hypothesis(Evidence.DEFAULT, _clear(case), "more than the balances: the text cited only part of it")


def _overpaid(case: Gap) -> Iterator[Hypothesis]:
    invoices = case.invoices
    if case.gap < 0 and len(invoices) == 1 and not case.notes and _is_overpayment(-case.gap, invoices[0][1]):
        yield Hypothesis(Evidence.BOUNDED, {invoices[0][0]: (invoices[0][1], "OVERPAYMENT")}, "excess within limits")


def _discounts(case: Gap) -> dict[str, int]:
    return {i: d for i, o, t in case.invoices if o == t.total_cents and (d := _discount_cents(t))}


def _discount_taken(case: Gap, taken: dict[str, int]) -> dict[str, tuple[int, str]]:
    """Within terms the invoice clears in full; late, what was left of it stays open."""
    out = {}
    for item, open_cents, terms in case.invoices:
        if item not in taken:
            out[item] = (open_cents, "")
        elif _in_terms(terms, case.booking_date):
            out[item] = (open_cents, "SHORT_DISCOUNT")
        else:
            out[item] = (open_cents - taken[item], "PARTIAL")
    return out


def _all_discounts(case: Gap) -> Iterator[Hypothesis]:
    discounts = _discounts(case) if case.gap > 0 else {}
    if discounts and abs(sum(discounts.values()) - case.gap) <= len(discounts):
        yield Hypothesis(Evidence.ALL_DISCOUNTS, _discount_taken(case, discounts), "the gap is their discounts")


def _one_discount(case: Gap) -> Iterator[Hypothesis]:
    for item, discount in (_discounts(case) if case.gap > 0 else {}).items():
        if abs(discount - case.gap) <= 1:
            yield Hypothesis(Evidence.ONE_DISCOUNT, _discount_taken(case, {item: discount}),
                             f"the gap is the discount of {item}, the rest paid as they are")


def _withheld_on_all(case: Gap) -> Iterator[Hypothesis]:
    invoices = case.invoices
    if case.gap <= 0 or not all(o == t.total_cents and t.country in WITHHOLDING_COUNTRIES for _, o, t in invoices):
        return
    for rate in WITHHOLDING_RATES:
        if abs(sum(round(t.total_cents * rate) for _, _, t in invoices) - case.gap) <= len(invoices):
            yield Hypothesis(Evidence.RATE_ON_ALL, {i: (o, "SHORT_WITHHOLDING") for i, o, _ in invoices},
                             f"the gap is {rate:.2%} of them all")


def _bank_fee(case: Gap) -> Iterator[Hypothesis]:
    if case.gap <= 0 or len(case.invoices) != 1 or case.eur_per_cent is None:
        return
    item, open_cents, terms = case.invoices[0]
    fee_ok = case.gap * case.eur_per_cent <= FEE_LIMIT_EUR_CENTS and case.gap <= open_cents * FEE_LIMIT_RATIO
    if fee_ok and terms.country and terms.country not in SEPA_COUNTRIES:
        yield Hypothesis(Evidence.MOVEMENT_MARK, {item: (open_cents, "SHORT_BANK_CHARGES")}, "a fee within the limits")


def _what_the_cash_reaches(case: Gap) -> Iterator[Hypothesis]:
    if case.gap > 0:
        available = case.cash + sum(o for _, o, _ in case.notes)
        yield Hypothesis(Evidence.DEFAULT, _oldest_first(available, case.invoices), "no clause explains the gap")


def _round_share(case: Gap) -> Iterator[Hypothesis]:
    """The invoice that, with the others cleared whole, takes a round share of its total: that one is the partial.

    A whole invoice's balance says nothing; a share to the cent does, as in PARTY-FRACTION. Two that fit tie and neither
    is taken; so is a share chance would explain. A document that lists the items already said where the money stops."""
    invoices = case.invoices
    if case.gap <= 0 or len(invoices) < 2 or any(t.listed_at is not None for _, _, t in invoices):
        return
    whole = [(i, o) for i, o, t in invoices if o == t.total_cents]
    if sum((ROUND_FRACTIONS - 1) * SHARE_WINDOW / max(o, 1) for _, o in whole) > MAX_CHANCE:
        return
    available = case.cash + sum(o for _, o, _ in case.notes) - sum(o for _, o, _ in invoices)
    for item, open_cents in whole:
        applied = available + open_cents
        if 0 < applied < open_cents and any(abs(applied * ROUND_FRACTIONS - open_cents * k) <= ROUND_FRACTIONS
                                            for k in range(1, ROUND_FRACTIONS)):
            yield Hypothesis(Evidence.ROUND_SHARE, {**_clear(case), item: (applied, "PARTIAL")},
                             f"{item} takes a round share, the rest paid whole")


# What can explain a gap. A new hypothesis is a function of a Gap that yields it, added here.
NODES = (_exact, _beyond_the_balances, _overpaid, _all_discounts, _one_discount, _withheld_on_all, _bank_fee,
         _round_share, _what_the_cash_reaches)


def _oldest_first(available: int, invoices: list) -> dict[str, tuple[int, str]]:
    """Cash no clause explains: by age, unless a document lists the items. Then in its order, because the payer wrote
    what it applied the payment to: what the money does not reach is the end of its own list (POLICIES §5.4)."""
    out = {}
    for item, open_cents, _ in sorted(invoices, key=lambda i: (i[2].listed_at or 0, i[2].issue_date or "", i[0])):
        applied = min(available, open_cents)
        if applied > 0:
            out[item] = (open_cents, "") if applied == open_cents else (applied, "PARTIAL")
        available -= applied
    return out

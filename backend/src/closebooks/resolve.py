"""Walk the bank lines by booking date, apply the best proposal, fix amount and exception, update balances."""
from __future__ import annotations

from dataclasses import replace

from .categories import fallback
from .load import Phase, cancelled_item_ids
from .model import Proposal, Row
from .policy import Terms, allocate, cross_border, decide
from .rules.party_amount import document_says
from .state import OpenBalances


def resolve(phase: Phase, proposals: dict[str, Proposal], stateful=None) -> tuple[list[Row], OpenBalances]:
    items = phase.items
    ids = items["item_id"].to_list()
    balances = OpenBalances(dict(zip(ids, items["open_cents"].to_list(), strict=True)),
                            dict(zip(ids, items["total_cents"].to_list(), strict=True)))
    currency = dict(zip(ids, items["currency"].to_list(), strict=True))
    party = dict(zip(ids, items["party_id"].to_list(), strict=True))
    terms_of = _terms_lookup(phase)
    # Settled by a rule that cited nothing: if the item is paid again, that first match is what is in doubt.
    settled_uncited: set[str] = set()
    # POLICIES §5.7: opens at 0 without having been paid, so paying it is not paying it again.
    cancelled = cancelled_item_ids(items) if "reason" in items.columns else set()
    plans = getattr(stateful, "clauses", {})
    rows: list[Row] = []
    for txn in phase.txns.select(
        "bank_txn_id", "booking_date", "amount_cents", "currency", "bank", "bank_code", "bank_subcode", "text",
        "orig_cents", "orig_currency", "amount_eur_cents", "entity", "counterparty_name", "counterparty_account",
        "remittance_info", "ref1", "ref2", "end_to_end_id"
    ).iter_rows(named=True):
        txn_id = txn["bank_txn_id"]
        proposal = proposals.get(txn_id)
        if proposal is None and stateful is not None:
            proposal = stateful(txn, balances)
        if proposal is None:
            out = fallback(txn)
            rows.append(Row(txn_id, None, None, None, out.category, out.exception or None, out.rule, out.confidence))
            continue
        if proposal.category:
            exception = "UNIDENTIFIED" if proposal.category == "UNIDENTIFIED" else None
            rows.append(Row(txn_id, None, None, None, proposal.category, exception, proposal.rule,
                            proposal.confidence, proposal.party_id, proposal.reference, proposal.sources,
                            proposal.candidates))
            continue
        decided = _by_cash(proposal, txn, currency, balances, terms_of, plans) if proposal.by_cash else None
        for item_id, applied in proposal.lines:
            if decided is not None:
                if item_id not in decided:
                    continue
                amount, exception = decided[item_id]
            else:
                amount, exception = decide(
                    item_id, currency[item_id], txn["currency"], balances.open(item_id), applied, proposal.returned,
                    deduction=proposal.deductions.get(item_id), terms=terms_of(item_id),
                    booking_date=txn["booking_date"])
            exception = _as_the_plan_says(plans.get(item_id), amount, len(proposal.lines), exception)
            balance_effect = exception
            doubts_first = item_id in settled_uncited and proposal.rule != "PARTY-DUPLICATE"
            if exception == "DUPLICATE_PAYMENT" and doubts_first:
                exception = ""
                settled_uncited.discard(item_id)
            elif exception == "DUPLICATE_PAYMENT" and item_id in cancelled and not balances.history(item_id):
                exception = ""
            elif proposal.rule.startswith("PARTY-"):
                settled_uncited.add(item_id)
            balances.apply(item_id, amount, balance_effect, txn_id, txn["booking_date"])
            rows.append(Row(txn_id, item_id, amount, currency[item_id], None, exception or None, proposal.rule,
                            proposal.confidence, party[item_id], proposal.reference, proposal.sources,
                            proposal.candidates))
    return rows, balances


def _as_the_plan_says(clauses: dict | None, amount: int, lines: int, exception: str) -> str:
    """POLICIES §3: every instalment but the last is PARTIAL, whatever our balance says (we may have missed one). Only
    instalments of different amounts say which one is being paid."""
    amounts = (clauses or {}).get("instalments", {}).get("amounts", ())
    if lines != 1 or exception not in ("", "PARTIAL") or len(set(amounts)) < 2 or amount not in amounts:
        return exception
    return "" if amount == amounts[-1] else "PARTIAL"


def _by_cash(proposal: Proposal, txn: dict, currency: dict, balances: OpenBalances, terms_of, plans: dict) -> dict:
    first = proposal.lines[0][0]
    foreign = currency[first] != txn["currency"]
    cash = abs(txn["amount_cents"])
    if foreign:
        cash = txn["orig_cents"] if txn["orig_currency"] == currency[first] else None
    total = terms_of(first).total_cents
    if len(proposal.lines) == 1 and cash is not None and balances.open(first) == total:
        said = document_says(plans.get(first), total, cash)
        if said is not None:  # the clause wins over any rate the shortfall happens to match (POLICIES §3)
            return {first: (cash, said)}
    from_abroad = not foreign and cross_border(txn["bank_code"], txn["text"])
    eur_per_cent = abs(txn["amount_eur_cents"]) / abs(txn["amount_cents"]) if from_abroad else None
    items = [(item, balances.open(item), terms_of(item)) for item, _ in proposal.lines]
    if proposal.in_listed_order:
        items = [(item, open_cents, replace(terms, listed_at=at)) for at, (item, open_cents, terms) in enumerate(items)]
    return allocate(cash, items, txn["booking_date"], foreign, eur_per_cent)


def _terms_lookup(phase: Phase):
    """Payment terms and country of an item, built only for the items a line touches."""
    items = phase.items
    index = {item: i for i, item in enumerate(items["item_id"].to_list())}
    codes, issued = items["payment_terms"].to_list(), items["issue_date"].to_list()
    totals, parties = items["total_cents"].to_list(), items["party_id"].to_list()
    master = phase.masters["payment_terms"]
    discounts = {row["code"]: (float(row["early_payment_discount_pct"]), int(row["discount_days"]))
                 for row in master.iter_rows(named=True) if row["early_payment_discount_pct"]}
    countries = dict(phase.masters["customers"].select("customer_id", "country").iter_rows())

    def terms_of(item_id: str) -> Terms:
        i = index[item_id]
        pct, days = discounts.get(codes[i], (None, None))
        return Terms(pct, days, issued[i], totals[i], countries.get(parties[i]))

    return terms_of

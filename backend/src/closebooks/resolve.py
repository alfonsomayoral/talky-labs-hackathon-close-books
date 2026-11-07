"""Walk the bank lines by booking date, apply the best proposal, fix amount and exception, update balances."""
from __future__ import annotations

from .categories import fallback
from .load import Phase
from .model import Proposal, Row
from .policy import Terms, allocate, decide
from .state import OpenBalances


def resolve(phase: Phase, proposals: dict[str, Proposal]) -> tuple[list[Row], OpenBalances]:
    items = phase.items
    ids = items["item_id"].to_list()
    balances = OpenBalances(dict(zip(ids, items["open_cents"].to_list(), strict=True)),
                            dict(zip(ids, items["total_cents"].to_list(), strict=True)))
    currency = dict(zip(ids, items["currency"].to_list(), strict=True))
    party = dict(zip(ids, items["party_id"].to_list(), strict=True))
    terms_of = _terms_lookup(phase)
    rows: list[Row] = []
    for txn in phase.txns.select(
        "bank_txn_id", "booking_date", "amount_cents", "currency", "bank", "bank_code", "bank_subcode", "text",
        "orig_cents", "orig_currency", "amount_eur_cents"
    ).iter_rows(named=True):
        txn_id = txn["bank_txn_id"]
        proposal = proposals.get(txn_id)
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
        decided = _by_cash(proposal, txn, currency, balances, terms_of) if proposal.by_cash else None
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
            balances.apply(item_id, amount, exception, txn_id, txn["booking_date"])
            rows.append(Row(txn_id, item_id, amount, currency[item_id], None, exception or None, proposal.rule,
                            proposal.confidence, party[item_id], proposal.reference, proposal.sources,
                            proposal.candidates))
    return rows, balances


def _by_cash(proposal: Proposal, txn: dict, currency: dict, balances: OpenBalances, terms_of) -> dict:
    first = proposal.lines[0][0]
    foreign = currency[first] != txn["currency"]
    cash = abs(txn["amount_cents"])
    if foreign:
        cash = txn["orig_cents"] if txn["orig_currency"] == currency[first] else None
    eur_per_cent = abs(txn["amount_eur_cents"]) / abs(txn["amount_cents"]) if not foreign else None
    items = [(item, balances.open(item), terms_of(item)) for item, _ in proposal.lines]
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

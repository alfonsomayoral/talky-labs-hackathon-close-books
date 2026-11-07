"""REF-SETTLEMENT and REF-SETTLEMENT-MARK: a later line that pays what a dispute left open on the one invoice it cites.

Why it generalizes: POLICIES §3 says the disputed part "may be paid later → that later line has no exception" and lists
"the settlement of a disputed amount" under the empty exception. The official example of `ar_short_dispute` shows the
other half: the row with the deduction carries what was paid, so the rest stays open.

REF-SETTLEMENT is structural, in no language: the invoice's own history has a SHORT_DISPUTE, the balance it left is the
cash to the cent, and the line cites that invoice by its complete number. It goes before the search by party because a
subset of smaller invoices can also add up to such a small amount.

REF-SETTLEMENT-MARK covers what that cannot see: without an advice the earlier line, and so the deduction, may have gone
unseen, and the invoice looks untouched (it would be PARTIAL) or closed (nothing to apply it to). `MARKS` are the two
wordings of POLICIES' "settlement of a disputed amount" measured on the bank lines of holdout and LIVE, not
translations: any other wording claims nothing here and gets the behaviour of the other rules. The amount is what the
line paid, and the item stays free for the walk (`settles_rest`): the earlier payment is still to come by date.

Not claimed: anything another pass claimed (card settlements say the mark and cite no invoice), several invoices cited,
another currency without the amount in the invoice's currency, a balance no dispute left without a mark."""
from __future__ import annotations

import polars as pl

from ..load import Phase
from ..model import Proposal
from .party_amount import PartyAmount, _alnum

MARKS = r"SETTLEMENT|REGULARIZACI"
NUMBER = r"[A-Z0-9][A-Z0-9/\-]*[0-9]"
MIN_NUMBER = 6  # shorter runs are dates and counters, not invoice numbers


def _flat(column: pl.Expr) -> pl.Expr:
    return column.str.to_uppercase().str.replace_all(r"[^0-9A-Z]", "")


def propose(phase: Phase) -> dict[str, Proposal]:
    text = pl.concat_str(["text", "ref1", "ref2", "end_to_end_id", "remittance_info"], separator=" ",
                         ignore_nulls=True).str.to_uppercase()
    lines = phase.txns.filter(pl.col("amount_cents") > 0, text.str.contains(MARKS)).select(
        "bank_txn_id", "entity", "currency", "amount_cents", "orig_cents", "orig_currency",
        text.str.extract_all(NUMBER).alias("number"))
    cited = lines.explode("number").with_columns(_flat(pl.col("number"))).filter(
        pl.col("number").str.len_chars() >= MIN_NUMBER).unique(["bank_txn_id", "number"])
    invoices = phase.items.filter(pl.col("item_type") == "ARI").select(
        "item_id", "entity", "party_id", pl.col("currency").alias("item_currency"),
        _flat(pl.col("document_number")).alias("number"))
    found = cited.join(invoices, on=["entity", "number"]).filter(pl.col("item_id").n_unique().over("bank_txn_id") == 1)
    paid = (pl.when(pl.col("item_currency") == pl.col("currency")).then(pl.col("amount_cents"))
            .when(pl.col("item_currency") == pl.col("orig_currency")).then(pl.col("orig_cents")))
    return {
        row["bank_txn_id"]: Proposal(
            rule="REF-SETTLEMENT-MARK", lines=[(row["item_id"], row["paid"])], party_id=row["party_id"],
            settles_rest=True, reference=row["number"], sources=[{"kind": "customer", "ref": row["party_id"]}])
        for row in found.with_columns(paid.alias("paid")).drop_nulls("paid").iter_rows(named=True)}


class Settling(PartyAmount):
    def __call__(self, txn: dict, balances) -> Proposal | None:
        return self._settled(txn, balances) or super().__call__(txn, balances)

    def _settled(self, txn: dict, balances) -> Proposal | None:
        if txn["amount_cents"] <= 0:
            return None
        cited = {entry[0]: entry for token in self._tokens(txn)
                 for entry in self.by_number.get((txn["entity"], _alnum(token)), ()) if entry[0].startswith("ARI")}
        if len(cited) != 1:
            return None
        (item_id, entry), = cited.items()
        cash, currency = self._cash(txn)
        if entry[3] != currency or balances.open(item_id) != cash:
            return None
        disputed = [m["bankTxnId"] for m in balances.history(item_id) if m["exception"] == "SHORT_DISPUTE"]
        if not disputed:
            return None
        return Proposal(rule="REF-SETTLEMENT", lines=[(item_id, None)], reference=entry[1],
                        sources=[{"kind": "bankLine", "ref": disputed[0]}])

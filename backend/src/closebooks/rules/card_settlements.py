"""R1: FILE-CARD and FILE-CARD-CHARGEBACK. A card settlement clears the orders of its file at gross, the acquirer fee is
not an exception (POLICIES §4); a chargeback reopens the order it reverses (§3 RETURNED)."""
from __future__ import annotations

import polars as pl

from ..load import Phase, load_detail
from ..model import Proposal
from .ar_common import applied_lines, by_number, cents, entity_of_account, invoices, tokens

CARD = r"\*{4}\d{4}"
SETTLEMENT_DAYS = 5  # the bank books a settlement on its date or within the days after


def _orders(phase: Phase) -> pl.DataFrame:
    """One row per card operation of every settlement, with its invoice when the order number identifies one."""
    settlements = load_detail(phase, "card_settlements")
    if settlements.is_empty():
        return settlements
    orders = (
        settlements.join(entity_of_account(phase), on="account_id", how="left")
        .with_columns(cents("gross").alias("cents"), cents("net").alias("net_cents"),
                      pl.col("order_number").alias("key"), pl.lit(None, pl.String).alias("party_id"))
        .with_row_index("rid"))
    return orders.join(by_number(orders, invoices(phase)), on="rid", how="left")


def propose(phase: Phase) -> dict[str, Proposal]:
    orders = _orders(phase)
    if orders.is_empty():
        return {}
    txns = phase.txns.select("bank_txn_id", "account_id", "booking_date", "amount_cents", "text", "ref1", "ref2",
                             "end_to_end_id", "remittance_info")
    return {**_settlements(txns, orders), **_chargebacks(txns, orders)}


def _settlements(txns: pl.DataFrame, orders: pl.DataFrame) -> dict[str, Proposal]:
    """The credit has the net of one settlement of its account, booked on its date or soon after, and names its
    merchant or settlement id (the id is the merchant's last digits and the date, the line may add more)."""
    settlements = orders.group_by("account_id", "settlement_id", "merchant_id", "settlement_date", "file").agg(
        pl.col("net_cents").sum())
    lag = (pl.col("booking_date").str.to_date() - pl.col("settlement_date").str.to_date()).dt.total_days()
    credits = txns.filter(pl.col("amount_cents") > 0)
    cited = tokens(credits).select("bank_txn_id", "digits")
    found = (
        credits.join(settlements, left_on=["account_id", "amount_cents"], right_on=["account_id", "net_cents"])
        .filter(lag.is_between(0, SETTLEMENT_DAYS))
        .join(cited, on="bank_txn_id")
        .filter((pl.col("digits") == pl.col("merchant_id")) | pl.col("digits").str.starts_with(pl.col("settlement_id")))
        .with_columns(lag.alias("lag"))
        .sort("bank_txn_id", "lag").unique("bank_txn_id", keep="first", maintain_order=True))
    lines = (
        found.join(orders.drop_nulls("item_id"), on=["account_id", "settlement_id"], suffix="_order")
        .group_by("bank_txn_id", "settlement_id", maintain_order=True)
        .agg(pl.col("item_id"), pl.col("cents"), pl.col("file").first()))
    return {
        row["bank_txn_id"]: Proposal(
            rule="FILE-CARD", lines=applied_lines(row["item_id"], row["cents"]), reference=row["settlement_id"],
            sources=[{"kind": "cardSettlement", "ref": row["file"], "label": row["settlement_id"]}])
        for row in lines.iter_rows(named=True)}


def _chargebacks(txns: pl.DataFrame, orders: pl.DataFrame) -> dict[str, Proposal]:
    """A debit naming a card and a merchant, with the gross of an operation settled before: that order comes back."""
    text = pl.concat_str(["text", "ref1", "ref2", "end_to_end_id", "remittance_info"], separator=" ", ignore_nulls=True)
    debits = txns.filter(pl.col("amount_cents") < 0).with_columns(
        pl.col("amount_cents").abs().alias("cents"), text.str.extract(f"({CARD})").alias("card"))
    named = debits.drop_nulls("card").join(tokens(debits).select("bank_txn_id", "digits"), on="bank_txn_id")
    found = (
        named.join(
            orders.drop_nulls("item_id").select("account_id", "card", "merchant_id", "cents", "settlement_date",
                                                "item_id", "file", "settlement_id"),
            left_on=["account_id", "card", "cents", "digits"], right_on=["account_id", "card", "cents", "merchant_id"])
        .filter(pl.col("settlement_date") <= pl.col("booking_date"))
        .sort("bank_txn_id", "settlement_date", descending=[False, True]).unique("bank_txn_id", keep="first",
                                                                              maintain_order=True))
    return {
        row["bank_txn_id"]: Proposal(
            rule="FILE-CARD-CHARGEBACK", lines=[(row["item_id"], row["cents"])], returned=True,
            reference=row["settlement_id"],
            sources=[{"kind": "cardSettlement", "ref": row["file"], "label": row["settlement_id"]}])
        for row in found.iter_rows(named=True)}

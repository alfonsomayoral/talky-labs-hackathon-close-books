"""R1: FILE-CHEQUE and FILE-CHEQUE-RETURN. A cheque or lockbox deposit clears the cheques of its file (POLICIES §5.3); a
returned cheque reopens the invoice of that cheque (§3 RETURNED)."""
from __future__ import annotations

import polars as pl

from ..load import Phase, load_detail
from ..model import Proposal
from .ar_common import applied_lines, by_attribute, by_number, cents, entity_of_account, invoices, tokens

CHEQUE_NUMBER = r"\d{6,}"


def _cheques(phase: Phase) -> pl.DataFrame:
    """One row per cheque of every deposit file, with its invoice when the stub, or the drawer and amount, say which."""
    deposits = load_detail(phase, "cheque_deposits")
    if deposits.is_empty():
        return deposits
    cheques = (
        deposits.join(entity_of_account(phase), on="account_id", how="left")
        .with_columns(cents("amount").alias("cents"), cents("deposit_total").alias("deposit_cents"),
                      pl.col("stub_reference").alias("key"), pl.lit(None, pl.String).alias("party_id"))
        .with_row_index("rid"))
    items = invoices(phase)
    resolved = by_number(cheques, items)
    pending = cheques.join(resolved.select("rid"), on="rid", how="anti")
    resolved = pl.concat([resolved, by_attribute(pending, items, "drawer", "party_name")])
    return cheques.join(resolved, on="rid", how="left")


def propose(phase: Phase) -> dict[str, Proposal]:
    cheques = _cheques(phase)
    if cheques.is_empty():
        return {}
    txns = phase.txns.select("bank_txn_id", "account_id", "booking_date", "amount_cents", "text", "ref1", "ref2",
                             "end_to_end_id", "remittance_info")
    return {**_deposits(txns, cheques), **_returns(txns, cheques)}


def _deposits(txns: pl.DataFrame, cheques: pl.DataFrame) -> dict[str, Proposal]:
    """The credit cites the deposit and has the total of its file. Deposit ids repeat across accounts: key with it."""
    credits = txns.filter(pl.col("amount_cents") > 0)
    found = tokens(credits).join(
        cheques.select("account_id", "deposit_id", "deposit_cents").unique(["account_id", "deposit_id"]),
        left_on=["account_id", "token"], right_on=["account_id", "deposit_id"]).join(
        credits.select("bank_txn_id", "amount_cents"), on="bank_txn_id").filter(
        pl.col("amount_cents") == pl.col("deposit_cents"))
    lines = (
        found.join(cheques.drop_nulls("item_id"), left_on=["account_id", "token"],
                   right_on=["account_id", "deposit_id"])
        .group_by("bank_txn_id", "token", maintain_order=True)
        .agg(pl.col("item_id"), pl.col("cents"), pl.col("file").first()))
    return {
        row["bank_txn_id"]: Proposal(
            rule="FILE-CHEQUE", lines=applied_lines(row["item_id"], row["cents"]), reference=row["token"],
            sources=[{"kind": "chequeDeposit", "ref": row["file"], "label": row["token"]}])
        for row in lines.iter_rows(named=True)}


def _returns(txns: pl.DataFrame, cheques: pl.DataFrame) -> dict[str, Proposal]:
    """A debit naming a cheque number, with the amount of that cheque, deposited before: that cheque comes back."""
    text = pl.concat_str(["text", "ref1", "ref2", "end_to_end_id", "remittance_info"], separator=" ", ignore_nulls=True)
    debits = txns.filter(pl.col("amount_cents") < 0).with_columns(pl.col("amount_cents").abs().alias("cents"))
    named = (
        debits.with_columns(text.str.extract_all(CHEQUE_NUMBER).alias("cheque_number")).explode("cheque_number")
        .drop_nulls("cheque_number").unique(["bank_txn_id", "cheque_number"]))
    found = (
        named.join(
            cheques.drop_nulls("item_id").select("account_id", "cheque_number", "cents", "deposit_date", "deposit_id",
                                                 "item_id", "file"),
            on=["account_id", "cheque_number", "cents"])
        .filter(pl.col("deposit_date") <= pl.col("booking_date"))
        .sort("bank_txn_id", "deposit_date", descending=[False, True]).unique("bank_txn_id", keep="first",
                                                                           maintain_order=True))
    return {
        row["bank_txn_id"]: Proposal(
            rule="FILE-CHEQUE-RETURN", lines=[(row["item_id"], row["cents"])], returned=True,
            reference=row["cheque_number"], sources=[{"kind": "chequeDeposit", "ref": row["file"],
                                                      "label": row["deposit_id"]}])
        for row in found.iter_rows(named=True)}

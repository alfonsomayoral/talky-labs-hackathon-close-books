"""R1: FILE-DD-BATCH and FILE-DD-RETURN. A direct-debit batch credit clears the receipts of its file (POLICIES §5.3);
a returned receipt reopens the invoice of the receipt it reverses (§3 RETURNED, §5.10)."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

import polars as pl

from ..load import Phase, load_detail
from ..model import Proposal
from .ar_common import MIN_SUFFIX, applied_lines, by_attribute, by_number, cents, entity_of_account, invoices, tokens
from .party_amount import PartyAmount, _alnum

# A mandate as the bank prints it: three or more hyphenated groups (VTM-ES-0004409).
MANDATE = r"[A-Z0-9]+(?:-[A-Z0-9]+){2,}"
# SEPA reason code of a refund claim by the debtor: it may come up to eight weeks after the collection.
REFUND_CLAIM = r"\bMD06\b"
MIN_DELAY = 2  # days between a collection and its return (none observed sooner)
LATE_DAYS = 15
REPRESENT_DAYS = 45  # a returned receipt presented again within this many days


def _receipts(phase: Phase) -> pl.DataFrame:
    """One row per receipt of every batch file, with its invoice when the number, or mandate and amount, say which."""
    batches = load_detail(phase, "direct_debit_batches")
    if batches.is_empty():
        return batches
    mandates = phase.masters["customers"].select(
        pl.col("sepa_mandate_id").alias("mandate_id"), pl.col("customer_id").alias("party_id")).drop_nulls().unique(
        "mandate_id")
    receipts = (
        batches.join(entity_of_account(phase), on="account_id", how="left").join(mandates, on="mandate_id", how="left")
        .with_columns(cents("amount").alias("cents"), cents("batch_total").alias("batch_cents"),
                      pl.col("remittance_info").str.extract(r"(\S+)\s*$").alias("key"))
        .with_row_index("rid"))
    items = invoices(phase)
    resolved = by_number(receipts, items)
    pending = receipts.join(resolved.select("rid"), on="rid", how="anti")
    resolved = pl.concat([resolved, by_attribute(pending, items.drop_nulls("item_party"), "party_id", "item_party")])
    return receipts.join(resolved, on="rid", how="left")


def propose(phase: Phase) -> dict[str, Proposal]:
    receipts = _receipts(phase)
    if receipts.is_empty():
        return {}
    txns = phase.txns.select("bank_txn_id", "account_id", "booking_date", "amount_cents", "text", "ref1", "ref2",
                             "end_to_end_id", "remittance_info")
    return {**_batches(txns, receipts), **_returns(txns, receipts, invoices(phase))}


def _batches(txns: pl.DataFrame, receipts: pl.DataFrame) -> dict[str, Proposal]:
    """Batch ids repeat across entities: the batch is (account, id), and the credit has the total of the file."""
    credits = txns.filter(pl.col("amount_cents") > 0)
    found = tokens(credits).join(
        receipts.select("account_id", "batch_id", "batch_cents").unique(["account_id", "batch_id"]),
        left_on=["account_id", "digits"], right_on=["account_id", "batch_id"]).join(
        credits.select("bank_txn_id", "amount_cents"), on="bank_txn_id").filter(
        pl.col("amount_cents") == pl.col("batch_cents"))
    lines = (
        found.join(receipts.drop_nulls("item_id"), left_on=["account_id", "digits"],
                   right_on=["account_id", "batch_id"])
        .group_by("bank_txn_id", "digits", maintain_order=True)
        .agg(pl.col("item_id"), pl.col("cents"), pl.col("file").first()))
    return {
        row["bank_txn_id"]: Proposal(
            rule="FILE-DD-BATCH", lines=applied_lines(row["item_id"], row["cents"]), reference=row["digits"],
            sources=[{"kind": "directDebitBatch", "ref": row["file"], "label": row["digits"]}])
        for row in lines.iter_rows(named=True)}


def _cites(flats: set[str], number: str) -> bool:
    """The whole number, or at least its last MIN_SUFFIX digits, as a citation counts on its own in `party_amount`."""
    digits = re.sub(r"\D", "", number)
    return _alnum(number) in flats or any(
        flat.isdigit() and len(flat.lstrip("0")) >= MIN_SUFFIX and digits.endswith(flat.lstrip("0")) for flat in flats)


def _paid_again(candidates: pl.DataFrame, txns: pl.DataFrame, items: pl.DataFrame) -> pl.DataFrame:
    """(bank_txn_id, item_id) of the receipt whose invoice a later transfer of that amount cites: its customer paid it
    another way because it came back (POLICIES §3, §5.10). Only where several could be the one returned, and only if
    one is cited: two say nothing.

    Why it generalizes: the evidence is the customer's own citation and the exact amount, in the days a returned receipt
    is presented again, with nothing learned from any phase."""
    several = candidates.filter(pl.col("item_id").n_unique().over("bank_txn_id") > 1).select(
        "bank_txn_id", "account_id", "cents", "booking_date", "item_id").unique()
    numbers = dict(items.select("item_id", "document_number").iter_rows())
    later: dict[tuple[str, int], list[tuple[str, set[str]]]] = defaultdict(list)
    for txn in txns.filter(pl.col("amount_cents").is_in(several["cents"].unique().to_list())).iter_rows(named=True):
        later[txn["account_id"], txn["amount_cents"]].append(
            (txn["booking_date"], {_alnum(t) for t in PartyAmount._tokens(txn)}))
    found = []
    for return_id, account, amount, booked, item in several.iter_rows():
        if any(0 < (date.fromisoformat(day) - date.fromisoformat(booked)).days <= REPRESENT_DAYS
               and _cites(flats, numbers.get(item) or "") for day, flats in later[account, amount]):
            found.append((return_id, item))
    return pl.DataFrame(found, schema={"bank_txn_id": pl.String, "item_id": pl.String}, orient="row").filter(
        pl.len().over("bank_txn_id") == 1).with_columns(pl.lit(True).alias("paid_again"))


def _returns(txns: pl.DataFrame, receipts: pl.DataFrame, items: pl.DataFrame) -> dict[str, Proposal]:
    """A debit naming a mandate, with the amount of a receipt: that receipt comes back.

    Of several receipts of the same mandate and amount collected before: the batch the debit cites; the only one whose
    invoice a later transfer cites; a delay as the reason says (a refund claim, MD06, comes weeks later; any other
    return within days); a receipt not presented again; the latest. A receipt comes back once. If none fits (its file
    is from before the phase), the receipt presented again soon after is the one that came back (§5.10)."""
    debits = txns.filter(pl.col("amount_cents") < 0).with_columns(pl.col("amount_cents").abs().alias("cents"))
    text = pl.concat_str(["text", "ref1", "ref2", "end_to_end_id", "remittance_info"], separator=" ", ignore_nulls=True)
    named = (
        debits.with_columns(text.str.extract_all(MANDATE).alias("mandate_id"),
                            text.str.contains(REFUND_CLAIM).alias("claim"))
        .explode("mandate_id").drop_nulls("mandate_id").unique(["bank_txn_id", "mandate_id"]))
    cited = tokens(debits).select("bank_txn_id", pl.col("digits").alias("batch_id"), pl.lit(True).alias("cited"))
    delay = (pl.col("booking_date").str.to_date() - pl.col("collection_date").str.to_date()).dt.total_days()
    in_time = pl.col("delay").is_between(MIN_DELAY, LATE_DAYS)
    on_time = pl.when(pl.col("claim")).then(pl.col("delay") >= LATE_DAYS).otherwise(in_time)
    presented_again = (pl.col("re_presentation") == "Y") & pl.col("delay").is_between(-REPRESENT_DAYS, -1)
    again = (receipts.filter(pl.col("re_presentation") == "Y").drop_nulls("item_id")
             .select("item_id", pl.col("collection_date").alias("again_date")))
    candidates = (
        named.join(
            receipts.drop_nulls("item_id").select("account_id", "mandate_id", "cents", "collection_date", "batch_id",
                                                  "item_id", "file", "re_presentation"),
            on=["account_id", "mandate_id", "cents"])
        .with_columns(delay.alias("delay"))
        .with_columns(
            pl.when(on_time).then(0).when(presented_again).then(1).when(pl.col("delay") >= MIN_DELAY).then(2)
            .alias("fit"))
        .drop_nulls("fit")
        .join(cited, on=["bank_txn_id", "batch_id"], how="left"))
    # A receipt presented again after this return is one that came back: it explains the second presentation.
    reopened = (
        candidates.join(again, on="item_id")
        .filter((pl.col("again_date") > pl.col("collection_date")) & (pl.col("again_date") >= pl.col("booking_date")))
        .select("bank_txn_id", "batch_id", "mandate_id").unique().with_columns(pl.lit(True).alias("reopened")))
    candidates = (
        candidates.join(reopened, on=["bank_txn_id", "batch_id", "mandate_id"], how="left")
        .join(_paid_again(candidates, txns, items), on=["bank_txn_id", "item_id"], how="left")
        .with_columns(pl.col("cited").fill_null(False), pl.col("reopened").fill_null(False),
                      pl.col("paid_again").fill_null(False),
                      (pl.col("re_presentation") == "N").alias("first_presentation"),
                      pl.col("delay").abs().alias("gap"))
        .sort("booking_date", "bank_txn_id", "cited", "paid_again", "fit", "reopened", "first_presentation", "gap",
              descending=[False, False, True, True, False, True, True, False]))
    proposals: dict[str, Proposal] = {}
    used: set[tuple[str, str]] = set()
    for _, rows in candidates.group_by("bank_txn_id", maintain_order=True):
        row = next((r for r in rows.iter_rows(named=True) if (r["batch_id"], r["mandate_id"]) not in used), None)
        if row is None:
            continue
        used.add((row["batch_id"], row["mandate_id"]))
        proposals[row["bank_txn_id"]] = Proposal(
            rule="FILE-DD-RETURN", lines=[(row["item_id"], row["cents"])], returned=True, reference=row["batch_id"],
            sources=[{"kind": "directDebitBatch", "ref": row["file"], "label": row["batch_id"]}])
    return proposals

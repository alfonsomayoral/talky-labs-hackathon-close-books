"""What the receivable file rules share: bank lines citing a file, and the invoice a file line points to."""
from __future__ import annotations

import polars as pl

from ..load import Phase

# A reference the bank may print with a prefix of letters (RCH…, DEV…) or cut at the end of a field.
TOKEN = r"[A-Za-z]{0,4}\d{8,}"
MIN_SUFFIX = 5


def cents(column: str) -> pl.Expr:
    return (pl.col(column).cast(pl.Float64) * 100).round().cast(pl.Int64)


def entity_of_account(phase: Phase) -> pl.DataFrame:
    return phase.masters["bank_accounts"].select("account_id", "entity")


def tokens(txns: pl.DataFrame, pattern: str = TOKEN) -> pl.DataFrame:
    """One row per reference found in the text of a bank line: the token and its digits (letters stripped)."""
    text = pl.concat_str(["text", "ref1", "ref2", "end_to_end_id", "remittance_info"], separator=" ", ignore_nulls=True)
    return (
        txns.select("bank_txn_id", "account_id", text.str.extract_all(pattern).alias("token"))
        .explode("token").drop_nulls("token")
        .with_columns(pl.col("token").str.replace(r"^\D+", "").alias("digits"))
        .unique(["bank_txn_id", "token"])
    )


def invoices(phase: Phase) -> pl.DataFrame:
    return phase.items.filter(pl.col("item_type") == "ARI").select(
        "item_id", "entity", pl.col("party_id").alias("item_party"), "party_name", "document_number", "total_cents",
        "currency")


def by_number(rows: pl.DataFrame, items: pl.DataFrame) -> pl.DataFrame:
    """`rows` (rid, entity, key, cents, party_id) -> (rid, item_id) for the lines whose number identifies one invoice.

    The number as printed first; else its trailing digits, when the line cuts the prefix, with the same amount.
    A line that points to several invoices is left out."""
    exact = rows.join(items, left_on=["entity", "key"], right_on=["entity", "document_number"])
    found = [exact]
    open_rows = rows.join(exact.select("rid").unique(), on="rid", how="anti").filter(
        pl.col("key").str.contains(r"^\d+$") & (pl.col("key").str.len_chars() >= MIN_SUFFIX))
    digits = items.with_columns(pl.col("document_number").str.replace_all(r"\D", "").alias("_digits"))
    for width in open_rows["key"].str.len_chars().unique().to_list():
        found.append(
            open_rows.filter(pl.col("key").str.len_chars() == width)
            .join(digits.with_columns(pl.col("_digits").str.slice(-width).alias("_tail")),
                  left_on=["entity", "key"], right_on=["entity", "_tail"])
            .filter(pl.col("cents") == pl.col("total_cents")))
    return _unique(pl.concat([f.select("rid", "item_id", "item_party", "party_id", "total_cents", "cents")
                              for f in found]))


def by_attribute(rows: pl.DataFrame, items: pl.DataFrame, row_column: str, item_column: str) -> pl.DataFrame:
    """Lines with no usable number: the customer (by id or printed name) and the exact amount."""
    joined = rows.drop_nulls(row_column).with_columns(pl.col(row_column).str.to_lowercase().alias("_k")).join(
        items.drop_nulls(item_column).with_columns(pl.col(item_column).str.to_lowercase().alias("_k")),
        on=["entity", "_k"]).filter(pl.col("cents") == pl.col("total_cents"))
    return _unique(joined.select("rid", "item_id", "item_party", "party_id", "total_cents", "cents"))


def _unique(found: pl.DataFrame) -> pl.DataFrame:
    """One invoice per line: with several, the one of the customer the line names, then the one of the same amount."""
    named = pl.col("party_id") == pl.col("item_party")
    found = found.filter(~named.any().over("rid") | named)
    same = pl.col("total_cents") == pl.col("cents")
    found = found.filter(~same.any().over("rid") | same)
    return found.filter(pl.len().over("rid") == 1).select("rid", "item_id")


def applied_lines(item_ids: list[str], amounts: list[int]) -> list[tuple[str, int]]:
    """A line of the file listed twice for one invoice is one line with the sum."""
    applied: dict[str, int] = {}
    for item_id, amount in zip(item_ids, amounts, strict=True):
        applied[item_id] = applied.get(item_id, 0) + amount
    return list(applied.items())

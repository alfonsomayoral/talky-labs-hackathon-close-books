# /// script
# requires-python = ">=3.12"
# dependencies = ["polars>=1.20"]
# ///
"""Volumes per phase, entity, account, statement format and currency; items and documents.

    uv run scripts/analysis/01_volumes.py [train live sample]
"""
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from common import detail_files, index_csv, md_table, phase_dir, section, table, write_json

phases = sys.argv[1:] or ["train", "live"]
summary = {}
for ph in phases:
    bt = table(ph, "bank_transactions")
    section(f"{ph}: movimientos")
    n = len(bt)
    credits = int((bt["amount"] > 0).sum())
    summary[ph] = {"txns": n, "credits": credits, "debits": n - credits,
                   "accounts": bt["account_id"].n_unique(), "entities": bt["entity"].n_unique(),
                   "currencies": sorted(bt["currency"].unique().to_list()),
                   "first": str(bt["booking_date"].min()), "last": str(bt["booking_date"].max())}
    print(f"{n:,} movimientos ({credits:,} cobros, {n-credits:,} pagos), {bt['account_id'].n_unique()} cuentas, "
          f"{bt['entity'].n_unique()} sociedades, {bt['currency'].n_unique()} divisas, "
          f"{bt['booking_date'].min()} → {bt['booking_date'].max()}")
    print()
    print(md_table(bt.group_by("statement_format").agg(pl.len().alias("txns"), pl.col("account_id").n_unique().alias("accounts"))
                   .sort("txns", descending=True)))
    print()
    print(md_table(bt.group_by("entity").agg(pl.len().alias("txns"), (pl.col("amount") > 0).sum().alias("credits"),
                                             pl.col("account_id").n_unique().alias("accounts"),
                                             pl.col("currency").unique().sort().str.join(" ").alias("currencies"))
                   .sort("txns", descending=True)))
    print()
    print(md_table(bt.group_by("currency").agg(pl.len().alias("txns"), pl.col("account_id").n_unique().alias("accounts"))
                   .sort("txns", descending=True)))
    print()
    print(md_table(bt.group_by("account_id", "entity", "bank", "statement_format", "currency").agg(pl.len().alias("txns"))
                   .sort("txns", descending=True)))
    print()
    print("camt-only columns present (%):",
          {c: round(100 * bt[c].is_not_null().mean(), 1) for c in ("counterparty_name", "counterparty_account", "end_to_end_id", "remittance_info", "orig_currency")})
    bt_year = bt.with_columns(pl.col("booking_date").dt.year().alias("year")).group_by("year").agg(pl.len().alias("txns")).sort("year")
    print(); print(md_table(bt_year))

    section(f"{ph}: partidas")
    rows = {}
    for name in ("ar_invoices", "ap_invoices", "credit_notes"):
        df = table(ph, name)
        rows[name] = len(df)
        print(f"{name}: {len(df):,} filas, {df['entity'].n_unique()} sociedades, divisas {sorted(df['currency'].unique().to_list())}")
        if name == "ar_invoices":
            print(md_table(df.group_by("payment_method").agg(pl.len().alias("n")).sort("n", descending=True)))
            print(md_table(df.group_by("payment_terms").agg(pl.len().alias("n")).sort("n", descending=True)))
            print(md_table(df.group_by("entity").agg(pl.len().alias("ar_invoices"), pl.col("customer_id").n_unique().alias("customers"),
                                                     pl.col("currency").unique().sort().str.join(" ").alias("currencies")).sort("ar_invoices", descending=True)))
            print(f"customer_po informado: {100 * df['customer_po'].is_not_null().mean():.1f} %")
        if name == "ap_invoices":
            print(md_table(df.group_by("payment_method").agg(pl.len().alias("n")).sort("n", descending=True)))
        if name == "credit_notes":
            print(md_table(df.group_by("side", "reason").agg(pl.len().alias("n")).sort("n", descending=True)))
            print(f"related_document informado: {100 * df['related_document'].is_not_null().mean():.1f} %")
    if (phase_dir(ph) / "open_items_at_start.csv.gz").exists():
        oi = table(ph, "open_items_at_start")
        rows["open_items_at_start"] = len(oi)
        print(f"open_items_at_start: {len(oi):,}")
        print(md_table(oi.group_by("item_type").agg(pl.len().alias("n"), (pl.col("open_amount") < pl.col("total_amount")).sum().alias("partially_paid")).sort("n", descending=True)))
    summary[ph]["items"] = rows

    section(f"{ph}: documentos de detalle")
    docs = {}
    for kind in ("direct_debit_batches", "card_settlements", "cheque_deposits", "payment_runs"):
        df = detail_files(ph, kind)
        key = {"direct_debit_batches": "batch_id", "card_settlements": "settlement_id", "cheque_deposits": "deposit_id", "payment_runs": "run_id"}[kind]
        docs[kind] = {"files": df["file"].n_unique(), "rows": len(df), "groups": df[key].n_unique()}
        extra = ""
        if kind == "payment_runs":
            extra = " · " + ", ".join(f"{k}: {v:,}" for k, v in df.group_by("run_type").agg(pl.len()).iter_rows())
        if kind == "direct_debit_batches":
            extra = " · " + ", ".join(f"{k}: {v:,}" for k, v in df.group_by("scheme").agg(pl.len()).iter_rows())
            extra += f" · re_presentation=Y: {(df['re_presentation'] == 'Y').sum():,}"
        print(f"{kind}: {docs[kind]['files']:,} ficheros, {docs[kind]['rows']:,} filas, {docs[kind]['groups']:,} {key}{extra}")
    ra = index_csv(ph, "remittance_advices")
    docs["remittance_advices"] = {"files": len(ra), "by_format": dict(ra.group_by("format").agg(pl.len()).iter_rows())}
    print(f"remittance_advices: {len(ra):,} ficheros · " + ", ".join(f"{k}: {v:,}" for k, v in sorted(docs['remittance_advices']['by_format'].items())))
    print(md_table(ra.group_by("entity").agg(pl.len().alias("advices"), pl.col("payer_name").n_unique().alias("payers")).sort("advices", descending=True)))
    pdfs = index_csv(ph, "pdfs")
    docs["pdfs"] = {"files": len(pdfs), "by_type": dict(pdfs.group_by("document_type").agg(pl.len()).iter_rows())}
    print(f"pdfs: {len(pdfs):,} ficheros · " + ", ".join(f"{k}: {v:,}" for k, v in sorted(docs['pdfs']['by_type'].items())))
    summary[ph]["documents"] = docs

write_json("01_volumes", summary)

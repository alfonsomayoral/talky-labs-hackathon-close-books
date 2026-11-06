# /// script
# requires-python = ">=3.12"
# dependencies = ["polars>=1.20"]
# ///
"""Drift TRAIN -> LIVE: Norma 43 -> camt.053 at Banco del Moncayo, remittance-advice layout change, ZA01/ZAR, IT01,
accounts and customers missing from the masters, bank text templates never seen in TRAIN, payment delay by year,
and whether live/open_items_at_start can be reproduced from TRAIN + golden.

    uv run scripts/analysis/04_drift.py
"""
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from common import index_csv, items, master, md_table, section, table, write_json

out = {}
bt_tr = table("train", "bank_transactions")
bt_lv = table("live", "bank_transactions")
month = lambda c: pl.col(c).dt.strftime("%Y-%m")

section("Banco del Moncayo: formato por mes en LIVE")
monc = bt_lv.filter(pl.col("bank") == "MONC").group_by(month("booking_date").alias("month"), "statement_format").agg(pl.len().alias("txns")).sort("month", "statement_format")
print(md_table(monc))
section("Banco del Moncayo: cómo cambia el texto (3 cobros de cliente por formato, misma cuenta)")
for fmt in ("n43", "camt053"):
    sample = bt_lv.filter((pl.col("account_id") == "ES01-MONC-EUR-2") & (pl.col("statement_format") == fmt) & (pl.col("amount") > 0)).head(3)
    for r in sample.select("bank_txn_id", "bank_code", "bank_subcode", "ref1", "ref2", "text", "counterparty_name", "remittance_info", "end_to_end_id").iter_rows(named=True):
        print(f"- `{fmt}` " + " · ".join(f"{k}=`{v}`" for k, v in r.items() if v))
section("Banco del Moncayo: códigos antes y después")
codes = bt_lv.filter(pl.col("bank") == "MONC").group_by("statement_format", "bank_code", "bank_subcode").agg(pl.len().alias("txns")).sort("txns", descending=True).head(16)
print(md_table(codes))
out["monc_by_month"] = monc.to_dicts()

section("Plantillas de texto nuevas en LIVE (primeras dos palabras del texto, por formato)")
tmpl = lambda df: df.with_columns(pl.col("text").fill_null("").str.extract(r"^(\S+\s+\S+)").str.to_uppercase().alias("tmpl"))
tr_t = tmpl(bt_tr).group_by("statement_format", "bank", "tmpl").agg(pl.len().alias("train_txns"))
lv_t = tmpl(bt_lv).group_by("statement_format", "bank", "tmpl").agg(pl.len().alias("live_txns"))
new = lv_t.join(tr_t, on=["statement_format", "bank", "tmpl"], how="left").filter(pl.col("train_txns").is_null()).sort("live_txns", descending=True)
print(f"movimientos de LIVE con una plantilla (formato, banco, 2 primeras palabras) nunca vista en TRAIN: {new['live_txns'].sum():,} de {len(bt_lv):,}")
print(md_table(new.head(20).drop("train_txns")))
out["new_templates_live_txns"] = int(new["live_txns"].sum())

section("Avisos de remesa: pagadores cuyo formato cambia en LIVE")
ra = index_csv("live", "remittance_advices").with_columns(pl.col("received_date").str.slice(0, 7).alias("month"))
by_payer = ra.group_by("payer_name", "entity").agg(pl.len().alias("advices"),
                                                   pl.col("format").filter(pl.col("month") < "2025-09").unique().sort().str.join("/").alias("before_sep"),
                                                   pl.col("format").filter(pl.col("month") >= "2025-09").unique().sort().str.join("/").alias("from_sep"))
changed = by_payer.filter((pl.col("before_sep") != "") & (pl.col("from_sep") != "") & (pl.col("before_sep") != pl.col("from_sep"))).sort("advices", descending=True)
print(md_table(changed.head(15)))
ra_tr = index_csv("train", "remittance_advices")
top_tr = ra_tr.group_by("payer_name").agg(pl.len().alias("train_advices")).sort("train_advices", descending=True).head(10)
print("\nlos 10 pagadores con más avisos en TRAIN y sus formatos en LIVE:")
print(md_table(top_tr.join(by_payer.drop("entity"), on="payer_name", how="left")))
print(md_table(ra.group_by("month", "format").agg(pl.len().alias("n")).sort("month", "format").pivot(on="format", index="month", values="n").fill_null(0)))

section("ZA01 en LIVE")
za = bt_lv.filter(pl.col("entity") == "ZA01")
for r in za.select("bank_txn_id", "account_id", "booking_date", "amount", "currency", "bank_code", "text", "counterparty_name", "remittance_info").iter_rows(named=True):
    print("- " + " · ".join(f"{k}=`{v}`" for k, v in r.items() if v))
accts = master("bank_accounts")
print(f"\ncuentas con movimientos que no están en masters/bank_accounts.csv · TRAIN: {sorted(set(bt_tr['account_id'].unique()) - set(accts['account_id']))} · LIVE: {sorted(set(bt_lv['account_id'].unique()) - set(accts['account_id']))}")
ents = master("entities")
print(f"sociedades con movimientos que no están en masters/entities.csv · LIVE: {sorted(set(bt_lv['entity'].unique()) - set(ents['entity']))}")
kwi = items("live").filter(pl.col("document_number").str.starts_with("KWI"))
print(f"partidas de LIVE con número KWI…: {len(kwi):,}")

section("IT01: cuentas y volumen por mes (TRAIN 2025 y LIVE)")
it01 = pl.concat([bt_tr.filter(pl.col("entity") == "IT01"), bt_lv.filter(pl.col("entity") == "IT01")]).filter(pl.col("booking_date") >= pl.date(2025, 1, 1))
print(md_table(it01.group_by(month("booking_date").alias("month"), "account_id").agg(pl.len().alias("txns"), (pl.col("amount") > 0).sum().alias("credits")).sort("month", "account_id").pivot(on="account_id", index="month", values="txns").fill_null(0)))

section("Terceros: clientes de LIVE que no existen en TRAIN ni en el maestro; nombres renombrados")
cust = master("customers")
ar_tr = table("train", "ar_invoices")
ar_lv = table("live", "ar_invoices")
new_cust = set(ar_lv["customer_id"].unique()) - set(ar_tr["customer_id"].unique())
not_in_master = set(ar_lv["customer_id"].unique()) - set(cust["customer_id"])
print(f"clientes facturados en LIVE: {ar_lv['customer_id'].n_unique():,} · nuevos respecto a TRAIN: {len(new_cust):,} · ausentes del maestro: {len(not_in_master):,}")
names = ar_lv.group_by("customer_id").agg(pl.col("customer_name").last().alias("invoice_name")).join(cust.select("customer_id", "name"), on="customer_id")
ren = names.filter(pl.col("invoice_name") != pl.col("name"))
print(f"clientes cuyo nombre en la factura de LIVE difiere del maestro: {len(ren):,} de {len(names):,}")
print(md_table(ren.head(8)))
ren_tr = ar_tr.group_by("customer_id").agg(pl.col("customer_name").n_unique().alias("names")).filter(pl.col("names") > 1)
print(f"clientes con más de un nombre en las facturas de TRAIN (renombrados): {len(ren_tr):,}")
blocked = cust.filter(pl.col("blocked_since").is_not_null())
print(f"clientes bloqueados en el maestro: {len(blocked):,} · proveedores bloqueados: {master('suppliers').filter(pl.col('blocked_since').is_not_null()).height:,}")
cp = bt_lv.filter(pl.col("counterparty_name").is_not_null()).select(pl.col("counterparty_name").str.to_uppercase().alias("n"))
master_names = set(cust["name"].str.to_uppercase()) | set(cust["trade_name"].drop_nulls().str.to_uppercase()) | set(master("suppliers")["name"].str.to_uppercase())
cp_hit = cp.with_columns(pl.col("n").is_in(list(master_names)).alias("hit"))
cp_tr = bt_tr.filter(pl.col("counterparty_name").is_not_null()).select(pl.col("counterparty_name").str.to_uppercase().alias("n")).with_columns(pl.col("n").is_in(list(master_names)).alias("hit"))
print(f"camt counterparty_name igual (exacto) a un nombre del maestro · TRAIN: {100 * cp_tr['hit'].mean():.1f} % · LIVE: {100 * cp_hit['hit'].mean():.1f} %")

section("Comportamiento de pago: días desde la emisión hasta el cobro (golden de TRAIN, facturas AR de una partida)")
g = table("train", "golden_allocations").filter(pl.col("item_id").str.starts_with("ARI"))
ar_dates = ar_tr.select("item_id", "issue_date", "due_date")
delay = g.join(ar_dates, on="item_id").join(bt_tr.select("bank_txn_id", "booking_date"), on="bank_txn_id") \
    .with_columns((pl.col("booking_date") - pl.col("issue_date")).dt.total_days().alias("days_issue"), (pl.col("booking_date") - pl.col("due_date")).dt.total_days().alias("days_due"), pl.col("booking_date").dt.year().alias("year"))
print(md_table(delay.group_by("year").agg(pl.len().alias("pairs"), pl.col("days_issue").median().alias("median_days_from_issue"), pl.col("days_due").median().alias("median_days_vs_due"),
                                          (100 * (pl.col("days_due") > 30).mean()).round(1).alias("pct_over_30d_late")).sort("year")))

section("¿Se reproduce live/open_items_at_start desde TRAIN + golden?")
oi = table("live", "open_items_at_start")
it_tr = items("train").select("item_id", "total_amount", "currency", "entity")
alloc = table("train", "golden_allocations").filter(pl.col("item_id").is_not_null()).with_columns(
    pl.when(pl.col("exception") == "RETURNED").then(-pl.col("amount")).when(pl.col("exception") == "DUPLICATE_PAYMENT").then(0.0).otherwise(pl.col("amount")).alias("applied"))
applied = alloc.group_by("item_id").agg(pl.col("applied").sum().alias("applied"), pl.col("exception").drop_nulls().unique().alias("excs"))
state = it_tr.join(applied, on="item_id", how="left").with_columns(pl.col("applied").fill_null(0.0)).with_columns((pl.col("total_amount") - pl.col("applied")).round(2).alias("open_calc"))
cmp = state.join(oi.select("item_id", "open_amount"), on="item_id", how="full", coalesce=True)
only_calc = cmp.filter(pl.col("open_amount").is_null() & (pl.col("open_calc") > 0.005))
only_oi = cmp.filter(pl.col("open_calc").is_null())
both = cmp.filter(pl.col("open_amount").is_not_null() & pl.col("open_calc").is_not_null())
diff = both.filter((pl.col("open_amount") - pl.col("open_calc")).abs() > 0.011)
print(f"partidas de TRAIN con saldo calculado > 0: {int((state['open_calc'] > 0.005).sum()):,} · en open_items_at_start: {len(oi):,}")
print(f"en ambos: {len(both):,} · solo calculadas (abiertas según nosotros, no en el fichero): {len(only_calc):,} · solo en el fichero (no son partidas de TRAIN): {len(only_oi):,} · importe distinto: {len(diff):,}")
print(md_table(diff.head(8).select("item_id", "total_amount", "applied", "open_calc", "open_amount")))
closed_in_file = both.filter(pl.col("open_calc") <= 0.005)
print(f"partidas que nosotros damos por cerradas pero el fichero trae abiertas: {len(closed_in_file):,}")
print(md_table(only_calc.head(6).select("item_id", "total_amount", "applied", "open_calc")))
over = state.filter(pl.col("open_calc") < -0.005)
print(f"partidas con saldo calculado negativo (se aplicó más que el total; OVERPAYMENT/duplicados mal contados): {len(over):,}")
out["open_items"] = {"calc_open": int((state["open_calc"] > 0.005).sum()), "file": len(oi), "both": len(both), "only_calc": len(only_calc), "only_file": len(only_oi), "amount_diff": len(diff)}
write_json("04_drift", out)

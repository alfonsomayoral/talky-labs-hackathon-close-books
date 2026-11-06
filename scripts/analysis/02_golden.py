# /// script
# requires-python = ">=3.12"
# dependencies = ["polars>=1.20"]
# ///
"""TRAIN golden by segment and difficulty, in movements and in pairs; exceptions and categories.

    uv run scripts/analysis/02_golden.py
"""
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from common import md_table, section, table, write_json

g = table("train", "golden_allocations")
bt = table("train", "bank_transactions").select("bank_txn_id", "entity", "bank", "amount", "currency", "statement_format", "booking_date")
g = g.join(bt, on="bank_txn_id", how="left")
pairs = g.filter(pl.col("item_id").is_not_null())
noitem = g.filter(pl.col("item_id").is_null())

section("totales")
n_txn = g["bank_txn_id"].n_unique()
print(f"filas del golden: {len(g):,} · movimientos: {n_txn:,} · pares: {len(pairs):,} · filas sin partida: {len(noitem):,}")
print(f"movimientos sin fila en el golden: {len(bt) - n_txn:,}")
per_txn = g.group_by("bank_txn_id").agg(pl.col("item_id").drop_nulls().len().alias("items"))
dist = per_txn.with_columns(pl.when(pl.col("items") == 0).then(pl.lit("0 (categoría)")).when(pl.col("items") == 1).then(pl.lit("1"))
                            .when(pl.col("items") <= 4).then(pl.lit("2-4")).when(pl.col("items") <= 9).then(pl.lit("5-9"))
                            .when(pl.col("items") <= 49).then(pl.lit("10-49")).otherwise(pl.lit("50+")).alias("items_per_txn")) \
    .group_by("items_per_txn").agg(pl.len().alias("txns"), pl.col("items").sum().alias("pairs")).sort("items_per_txn")
print(md_table(dist))
print(f"máximo de partidas en un movimiento: {per_txn['items'].max():,}")
print(md_table(pairs.with_columns(pl.col("item_id").str.slice(0, 3).alias("item_type")).group_by("item_type").agg(pl.len().alias("pairs")).sort("pairs", descending=True)))

section("por dificultad (movimientos)")
diff = g.group_by("bank_txn_id").agg(pl.col("difficulty").first()).group_by("difficulty").agg(pl.len().alias("txns")).sort("difficulty")
print(md_table(diff.with_columns((100 * pl.col("txns") / n_txn).round(1).alias("pct"))))

section("por segmento")
seg_txn = g.group_by("bank_txn_id").agg(pl.col("segment").first(), pl.col("difficulty").first(), pl.col("item_id").drop_nulls().len().alias("items"),
                                        pl.col("amount").sum().alias("golden_amount_sum"))
seg = seg_txn.group_by("segment").agg(pl.len().alias("txns"), pl.col("items").sum().alias("pairs"),
                                      pl.col("difficulty").mean().round(2).alias("difficulty"),
                                      pl.col("items").mean().round(1).alias("items_per_txn"),
                                      pl.col("items").max().alias("max_items"))
exc_by_seg = pairs.group_by("segment", "exception").agg(pl.len().alias("n"))
exc_pivot = exc_by_seg.with_columns(pl.col("exception").fill_null("(vacía)")).pivot(on="exception", index="segment", values="n").fill_null(0)
cat_by_seg = noitem.group_by("segment").agg(pl.col("category").mode().first().alias("top_category"), pl.col("exception").mode().first().alias("noitem_exception"))
seg = seg.join(cat_by_seg, on="segment", how="left").with_columns(
    (100 * pl.col("txns") / n_txn).round(2).alias("pct_txns"), (100 * pl.col("pairs") / len(pairs)).round(2).alias("pct_pairs")).sort("txns", descending=True)
print(md_table(seg.select("segment", "txns", "pct_txns", "pairs", "pct_pairs", "items_per_txn", "max_items", "difficulty", "top_category")))
print(f"\nsegmentos: {seg.height}")

section("excepciones por segmento (filas con partida; columnas = excepción)")
print(md_table(exc_pivot.join(seg.select("segment", "txns"), on="segment").sort("txns", descending=True).drop("txns")))

section("excepciones (filas)")
exc = g.with_columns(pl.col("exception").fill_null("")).filter(pl.col("exception") != "").group_by("exception").agg(
    pl.len().alias("rows"), pl.col("bank_txn_id").n_unique().alias("txns"), pl.col("segment").n_unique().alias("segments"))
top_seg = g.filter(pl.col("exception").is_not_null()).group_by("exception", "segment").agg(pl.len().alias("n")).sort("n", descending=True) \
    .group_by("exception").agg(pl.col("segment").head(3).str.join(", ").alias("top_segments"))
print(md_table(exc.join(top_seg, on="exception").sort("rows", descending=True)))

section("categorías (filas sin partida)")
cat = noitem.group_by("category").agg(pl.len().alias("rows"), pl.col("segment").n_unique().alias("segments"),
                                      (pl.col("amount_right") if "amount_right" in noitem.columns else pl.col("amount")).abs().sum().round(0).alias("abs_amount_sum_mixed_ccy"))
print(md_table(cat.sort("rows", descending=True)))

section("por sociedad y por formato (movimientos del golden)")
print(md_table(seg_txn.join(bt, on="bank_txn_id").group_by("entity").agg(pl.len().alias("txns"), pl.col("items").sum().alias("pairs"), pl.col("difficulty").mean().round(2).alias("difficulty")).sort("txns", descending=True)))
print(md_table(seg_txn.join(bt, on="bank_txn_id").group_by("statement_format").agg(pl.len().alias("txns"), pl.col("items").sum().alias("pairs"), pl.col("difficulty").mean().round(2).alias("difficulty")).sort("txns", descending=True)))

section("segmentos por sociedad (las 5 mayores por segmento)")
by_ent = seg_txn.join(bt, on="bank_txn_id").group_by("segment", "entity").agg(pl.len().alias("n")).sort("n", descending=True) \
    .group_by("segment").agg(pl.concat_str(pl.col("entity"), pl.lit(" "), pl.col("n").cast(pl.Utf8)).head(5).str.join(", ").alias("entities"))
print(md_table(by_ent.join(seg.select("segment", "txns"), on="segment").sort("txns", descending=True).drop("txns")))

write_json("02_golden", {"txns": n_txn, "pairs": len(pairs), "noitem": len(noitem),
                         "segments": seg.to_dicts(), "exceptions": exc.to_dicts(), "categories": cat.to_dicts(),
                         "difficulty": diff.to_dicts(), "items_per_txn": dist.to_dicts()})

section("movimientos sin partida: ¿basta el código del banco? pureza de la categoría por (banco, bank_code, bank_subcode)")
codes = noitem.join(bt.select("bank_txn_id", "bank"), on="bank_txn_id").join(table("train", "bank_transactions").select("bank_txn_id", "bank_code", "bank_subcode"), on="bank_txn_id") \
    .group_by("bank", "bank_code", "bank_subcode").agg(pl.len().alias("rows"), pl.col("category").n_unique().alias("categories"), pl.col("category").mode().first().alias("top_category"),
                                                      (pl.col("category") == pl.col("category").mode().first()).sum().alias("top_rows"))
pure = codes.with_columns((100 * pl.col("top_rows") / pl.col("rows")).round(1).alias("purity")).sort("rows", descending=True)
print(f"combinaciones (banco, código, subcódigo) en filas sin partida: {len(pure):,} · filas cuya categoría es la mayoritaria de su combinación: {100 * pure['top_rows'].sum() / pure['rows'].sum():.1f} %")
print(md_table(pure.head(25)))
mixed = pure.filter(pl.col("categories") > 1).sort("rows", descending=True)
print(f"\ncombinaciones con más de una categoría: {len(mixed):,}, con {mixed['rows'].sum():,} filas")
print(md_table(mixed.head(12)))
# and how often does a code used by no-item lines also appear on lines WITH items?
all_codes = table("train", "bank_transactions").select("bank_txn_id", "bank", "bank_code", "bank_subcode").join(per_txn, on="bank_txn_id") \
    .group_by("bank", "bank_code", "bank_subcode").agg(pl.len().alias("txns"), (pl.col("items") == 0).sum().alias("noitem_txns"))
shared = all_codes.filter((pl.col("noitem_txns") > 0) & (pl.col("noitem_txns") < pl.col("txns"))).sort("txns", descending=True)
print(f"\ncódigos que mezclan movimientos con y sin partida: {len(shared):,} combinaciones, {shared['txns'].sum():,} movimientos")
print(md_table(shared.head(12).with_columns((100 * pl.col("noitem_txns") / pl.col("txns")).round(1).alias("pct_noitem"))))

section("muestra de textos de ar_ref_noise por formato")
sample = seg_txn.filter(pl.col("segment") == "ar_ref_noise").join(table("train", "bank_transactions").select("bank_txn_id", "statement_format", "text", "remittance_info", "counterparty_name", "ref1", "ref2"), on="bank_txn_id")
for fmt in ("n43", "mt940", "camt053"):
    for r in sample.filter(pl.col("statement_format") == fmt).sample(4, seed=7).select("statement_format", "text", "counterparty_name", "remittance_info", "ref2").iter_rows(named=True):
        print("- " + " · ".join(f"{k}=`{v}`" for k, v in r.items() if v))

# /// script
# requires-python = ">=3.12"
# dependencies = ["polars>=1.20"]
# ///
"""Score a TRAIN submission with the official scorer and compute, per segment, how many points it would gain if that
segment were perfect (ceiling from this submission) and how many it would lose if everything else were perfect and
only that segment stayed as submitted (loss from perfect).

    uv run scripts/analysis/05_baseline.py runs/baseline/starter_train.csv.gz [--verify ar_dd_batch,ar_ref_noise]

The decomposition reimplements bankrec_score.py in Polars and asserts that it reproduces the official numbers.
"""
import argparse
import csv
import gzip
import sys
import time
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from common import EXCEPTIONS, MASTERS, PKG, md_table, section, table, write_json

sys.path.insert(0, str(PKG / "starter"))
import bankrec_score as S

W_ALLOC, W_TXN, W_EXC = 0.5, 0.3, 0.2


def official(golden_path: Path, txns_path: Path, sub_path: Path) -> dict:
    with open(MASTERS / "categories.csv", encoding="utf-8") as fh:
        cats = [r["category"] for r in csv.DictReader(fh)]
    # Local use only: the server limit is 60 MB uncompressed, which a TRAIN submission with ~5.4 M rows exceeds.
    # The metric is identical; only the size guard is relaxed.
    S.MAX_UNCOMPRESSED = S.MAX_DECOMPRESS = 1024 * 1024 * 1024
    t0 = time.time()
    g = S.load_golden(str(golden_path), str(txns_path), EXCEPTIONS, cats)
    t1 = time.time()
    res = S.score_submission(g, sub_path.read_bytes(), sub_path.name)
    res["timing"] = {"load_golden_s": round(t1 - t0, 1), "score_s": round(time.time() - t1, 1)}
    return res


def score(tp, sub, gp, ok, n, exc):
    """exc: dict class -> (tp, fp, gold)."""
    p = tp / sub if sub else 0.0
    r = tp / gp if gp else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    acc = ok / n
    f1s = []
    for etp, efp, egold in exc.values():
        if not egold:
            continue
        p_ = etp / (etp + efp) if etp + efp else 0.0
        r_ = etp / egold
        f1s.append(2 * p_ * r_ / (p_ + r_) if p_ + r_ else 0.0)
    macro = sum(f1s) / len(f1s) if f1s else 1.0
    return round(100 * (W_ALLOC * f1 + W_TXN * acc + W_EXC * macro), 2), f1, acc, macro


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("submission")
    ap.add_argument("--verify", default="", help="comma-separated segments to verify with the official scorer")
    a = ap.parse_args()
    sub_path = Path(a.submission)

    g = table("train", "golden_allocations")
    bt = table("train", "bank_transactions").select("bank_txn_id")
    sub = pl.read_csv(sub_path, infer_schema_length=0).with_columns(pl.col("amount").cast(pl.Float64, strict=False),
                                                                    pl.col("category").fill_null("").str.to_uppercase(), pl.col("exception").fill_null("").str.to_uppercase())
    g = g.with_columns(pl.col("category").fill_null(""), pl.col("exception").fill_null(""))
    seg_of = g.group_by("bank_txn_id").agg(pl.col("segment").first())
    g_pairs = g.filter(pl.col("item_id").is_not_null()).select("bank_txn_id", "item_id", pl.col("amount").alias("g_amount"), pl.col("exception").alias("g_exc"))
    g_noitem = g.filter(pl.col("item_id").is_null()).select("bank_txn_id", pl.col("category").alias("g_cat"), pl.col("exception").alias("g_exc"))
    s_pairs = sub.filter(pl.col("item_id").is_not_null()).join(g_pairs, on=["bank_txn_id", "item_id"], how="left").with_columns(
        (pl.col("g_amount").is_not_null() & ((pl.col("amount") - pl.col("g_amount")).abs() <= pl.max_horizontal(pl.lit(0.01), 0.005 * pl.col("g_amount").abs()) + 1e-9)).alias("tp"))
    s_pairs = s_pairs.with_columns((pl.col("tp") & (pl.col("exception") == pl.col("g_exc"))).alias("tp_exc"))
    s_noitem = sub.filter(pl.col("item_id").is_null())

    # per txn
    gi = g_pairs.group_by("bank_txn_id").agg(pl.len().alias("g_items"))
    si = s_pairs.group_by("bank_txn_id").agg(pl.len().alias("s_items"), pl.col("tp_exc").sum().alias("s_ok"))
    sn = s_noitem.group_by("bank_txn_id").agg(pl.len().alias("s_noitem"), pl.col("category").first().alias("s_cat"), pl.col("exception").first().alias("s_exc"))
    txn = bt.join(seg_of, on="bank_txn_id", how="left").join(gi, on="bank_txn_id", how="left").join(g_noitem, on="bank_txn_id", how="left") \
        .join(si, on="bank_txn_id", how="left").join(sn, on="bank_txn_id", how="left").fill_null(0)
    txn = txn.with_columns(pl.when(pl.col("g_items") > 0)
                           .then((pl.col("s_noitem") == 0) & (pl.col("s_items") == pl.col("g_items")) & (pl.col("s_ok") == pl.col("g_items")))
                           .otherwise((pl.col("s_noitem") > 0) & (pl.col("s_items") == 0) & (pl.col("s_cat") == pl.col("g_cat")) & (pl.col("s_exc") == pl.col("g_exc"))).alias("ok"))

    # exceptions per class and segment: tp, fp (submitted rows), gold
    ex_pairs = s_pairs.join(seg_of, on="bank_txn_id").filter(pl.col("exception") != "").with_columns((pl.col("exception") == pl.col("g_exc")).alias("hit"))
    ex_noitem = s_noitem.join(seg_of, on="bank_txn_id").join(g_noitem, on="bank_txn_id", how="left").join(gi, on="bank_txn_id", how="left") \
        .filter(pl.col("exception") != "").with_columns((pl.col("g_items").is_null() & (pl.col("exception") == pl.col("g_exc"))).alias("hit"))
    ex_sub = pl.concat([ex_pairs.select("segment", "exception", "hit"), ex_noitem.select("segment", "exception", "hit")]) \
        .group_by("segment", "exception").agg(pl.col("hit").sum().alias("tp"), (~pl.col("hit")).sum().alias("fp"))
    ex_gold = g.filter(pl.col("exception") != "").group_by("segment", "exception").agg(pl.len().alias("gold"))
    ex = ex_gold.join(ex_sub, on=["segment", "exception"], how="full", coalesce=True).fill_null(0)

    # per segment components
    seg = txn.group_by("segment").agg(pl.len().alias("n"), pl.col("ok").sum().alias("ok"), pl.col("g_items").sum().alias("gold_pairs"))
    seg = seg.join(s_pairs.join(seg_of, on="bank_txn_id").group_by("segment").agg(pl.len().alias("sub_pairs"), pl.col("tp").sum().alias("tp")), on="segment", how="left").fill_null(0)
    N, TP, SUB, GP, OK = len(txn), int(seg["tp"].sum()), int(seg["sub_pairs"].sum()), int(seg["gold_pairs"].sum()), int(seg["ok"].sum())
    exc_tot = {c: (0, 0, 0) for c in EXCEPTIONS}
    for c, tp_, fp_, gold_ in ex.group_by("exception").agg(pl.col("tp").sum(), pl.col("fp").sum(), pl.col("gold").sum()).iter_rows():
        exc_tot[c] = (int(tp_), int(fp_), int(gold_))
    base, f1, acc, macro = score(TP, SUB, GP, OK, N, exc_tot)

    section("puntuación oficial")
    txns_path = Path("runs/analysis/train_txn_ids.csv.gz")
    if not txns_path.exists():
        with gzip.open(txns_path, "wt") as fh:
            fh.write("bank_txn_id\n" + "\n".join(bt["bank_txn_id"].to_list()) + "\n")
    off = official(Path("db/train/golden_allocations.csv.gz"), txns_path, sub_path)
    print(f"`{sub_path.name}`: score {off['score']} · " + " · ".join(f"{k} {v}" for k, v in off["metrics"].items()) + f" · timing {off['timing']}")
    print(f"réplica en Polars: score {base} · f1 {f1:.6f} · acc {acc:.6f} · macro {macro:.6f}")
    assert abs(base - off["score"]) < 0.011, "la réplica no reproduce al evaluador oficial"
    print(md_table(pl.DataFrame({"exception": list(exc_tot), "tp": [v[0] for v in exc_tot.values()], "fp": [v[1] for v in exc_tot.values()], "gold": [v[2] for v in exc_tot.values()]})))

    # ceilings
    rows = []
    ex_by_seg = {s: {} for s in seg["segment"]}
    for s, c, tp_, fp_, gold_ in ex.select("segment", "exception", "tp", "fp", "gold").iter_rows():
        ex_by_seg.setdefault(s, {})[c] = (tp_, fp_, gold_)
    for s, n, ok, gp_s, sub_s, tp_s in seg.select("segment", "n", "ok", "gold_pairs", "sub_pairs", "tp").iter_rows():
        exc_up = dict(exc_tot)
        for c, (etp, efp, egold) in ex_by_seg.get(s, {}).items():
            t, f, gg = exc_up[c]
            exc_up[c] = (t + (egold - etp), f - efp, gg)
        up, *_ = score(TP + (gp_s - tp_s), SUB + (gp_s - sub_s), GP, OK + (n - ok), N, exc_up)
        exc_dn = {c: (gg, 0, gg) for c, (_, _, gg) in exc_tot.items()}
        for c, (etp, efp, egold) in ex_by_seg.get(s, {}).items():
            t, f, gg = exc_dn[c]
            exc_dn[c] = (t - (egold - etp), f + efp, gg)
        dn, *_ = score(GP - (gp_s - tp_s), GP - gp_s + sub_s, GP, N - (n - ok), N, exc_dn)
        rows.append({"segment": s, "txns": n, "pairs": gp_s, "acc_now": round(ok / n, 3), "pair_recall_now": round(tp_s / gp_s, 3) if gp_s else None,
                     "gain_if_perfect": round(up - base, 2), "loss_if_only_this_fails": round(100 - dn, 2)})
    df = pl.DataFrame(rows).sort("gain_if_perfect", descending=True)
    section(f"techo por segmento (base {base}): puntos que sube la puntuación global si el segmento se resuelve perfecto, "
            "y puntos que se pierden si todo lo demás es perfecto y este segmento se queda como está")
    print(md_table(df))
    print(f"\nsuma de las ganancias marginales: {df['gain_if_perfect'].sum():.2f} (no es aditiva: el F1 y la macro-F1 no son lineales); 100 − base = {100 - base:.2f}")
    write_json("05_ceilings", {"submission": sub_path.name, "official": off, "replica": {"score": base, "f1": f1, "acc": acc, "macro": macro}, "segments": rows})

    if a.verify:
        section("verificación con el evaluador oficial: el fichero base con un segmento sustituido por el golden")
        for s in a.verify.split(","):
            ids = set(seg_of.filter(pl.col("segment") == s)["bank_txn_id"].to_list())
            rest = sub.filter(~pl.col("bank_txn_id").is_in(list(ids)))
            gold_s = g.filter(pl.col("segment") == s).select("bank_txn_id", "item_id", "amount", "category", "exception")
            merged = pl.concat([rest.select("bank_txn_id", "item_id", "amount", "category", "exception"), gold_s]).with_columns(
                pl.when(pl.col("amount").is_not_null()).then(pl.col("amount").round(2).cast(pl.Utf8)).otherwise(pl.lit("")).alias("amount"))
            p = Path(f"runs/analysis/verify_{s}.csv.gz")
            p.write_bytes(gzip.compress(merged.write_csv(quote_style="never").encode("utf-8")))
            print(f"- `{s}`: {p.stat().st_size / 1e6:.1f} MB comprimido, {len(merged.write_csv(quote_style='never')) / 1e6:.1f} MB sin comprimir, {len(merged):,} filas")
            res = official(Path("db/train/golden_allocations.csv.gz"), txns_path, p)
            pred = base + df.filter(pl.col("segment") == s)["gain_if_perfect"][0]
            print(f"- `{s}`: oficial {res['score']} · predicho {pred:.2f}")


if __name__ == "__main__":
    main()

# /// script
# requires-python = ">=3.12"
# dependencies = ["polars>=1.20", "openpyxl", "pypdf"]
# ///
"""Which source can resolve each TRAIN segment.

For every golden pair (bank line, item) it checks where the item's printed number can be found:
  - text_strict   : the printed number, normalised (A-Z0-9), inside the bank text/ref1/ref2/remittance_info
  - text_digits   : its longest digit run (>= 5 digits) inside the bank text (number without prefix)
  - detail_file   : inside a direct-debit batch, card settlement, cheque deposit or payment-run file
  - remittance    : inside any remittance advice of the phase (csv, txt, xlsx and pdf are read as text)
  - pdf           : the item has a PDF in pdfs/index.csv
and per bank line: amount_exact (|amount| == sum of golden amounts, same currency), orig_currency present,
counterparty_name present, and how many invoices of the same entity/currency/total issued in the previous
400 days compete for a single-item line.

    uv run scripts/analysis/03_sources.py [train|sample]
"""
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from common import CACHE, detail_files, index_csv, items, md_table, norm_expr, phase_dir, section, table, write_json

phase = sys.argv[1] if len(sys.argv) > 1 else "train"
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9/\-_.]{3,}")


def ra_tokens(path: str) -> set[str]:
    """Alnum tokens (normalised) of one remittance advice, whatever its format."""
    p = Path(path)
    try:
        if p.suffix in (".csv", ".txt"):
            text = p.read_text(encoding="utf-8", errors="replace")
        elif p.suffix == ".xlsx":
            import openpyxl
            wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
            text = "\n".join(" ".join("" if v is None else str(v) for v in row) for ws in wb.worksheets for row in ws.iter_rows(values_only=True))
        elif p.suffix == ".pdf":
            from pypdf import PdfReader
            text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
        else:
            return set()
    except Exception:  # noqa: BLE001 - an unreadable advice just contributes no tokens
        return set()
    out = set()
    for tok in TOKEN.findall(text):
        n = re.sub(r"[^A-Z0-9]", "", tok.upper())
        if len(n) >= 5:
            out.add(n)
    return out


def remittance_token_table() -> pl.DataFrame:
    dst = CACHE / phase / "ra_tokens.parquet"
    if dst.exists():
        return pl.read_parquet(dst)
    idx = index_csv(phase, "remittance_advices")
    paths = [str(phase_dir(phase) / "remittance_advices" / f) for f in idx["file"].to_list()]
    toks = set()
    with ProcessPoolExecutor() as ex:
        for s in ex.map(ra_tokens, paths, chunksize=64):
            toks |= s
    df = pl.DataFrame({"tok": sorted(toks)})
    dst.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(dst)
    return df



def main() -> None:
    g = table(phase, "golden_allocations")
    bt = table(phase, "bank_transactions")
    it = items(phase).with_columns(norm_expr("document_number").alias("num_norm"),
                                   norm_expr("party_name").str.slice(0, 10).alias("name10"),
                                   pl.col("document_number").str.extract_all(r"\d{5,}").list.eval(pl.element().sort_by(pl.element().str.len_chars(), descending=True)).list.first().alias("num_digits"))
    pdf_idx = index_csv(phase, "pdfs").select("entity", norm_expr("document_number").alias("num_norm"), pl.lit(True).alias("pdf")).unique()

    bt = bt.with_columns(
        pl.concat_str([pl.col(c).fill_null("") for c in ("text", "ref1", "ref2", "remittance_info", "counterparty_name")], separator=" ")
          .str.to_uppercase().str.replace_all(r"[^A-Z0-9]", "").alias("text_norm"),
        pl.col("amount").abs().alias("abs_amount"))

    # --- detail files: one normalised token set (strict and digit runs)
    detail = []
    for kind, cols in (("direct_debit_batches", ["remittance_info"]), ("card_settlements", ["order_number"]),
                       ("cheque_deposits", ["stub_reference"]), ("payment_runs", ["document_number", "remittance_info"])):
        df = detail_files(phase, kind)
        for c in cols:
            detail.append(df.select(pl.col(c).fill_null("").str.to_uppercase().str.extract_all(r"[A-Z0-9][A-Z0-9/\-_.]*").alias("tok")).explode("tok")
                          .select(pl.col("tok").str.replace_all(r"[^A-Z0-9]", "").alias("tok")).filter(pl.col("tok").str.len_chars() >= 5))
    detail_tok = pl.concat(detail).unique().with_columns(pl.lit(True).alias("detail_file"))
    print(f"tokens de ficheros de detalle: {len(detail_tok):,}", file=sys.stderr)
    ra_tok = remittance_token_table().with_columns(pl.lit(True).alias("remittance"))
    print(f"tokens de avisos de remesa: {len(ra_tok):,}", file=sys.stderr)

    pairs = (g.filter(pl.col("item_id").is_not_null())
             .join(it, on="item_id", how="left", suffix="_item")
             .join(bt.select("bank_txn_id", "text_norm", "abs_amount", pl.col("currency").alias("txn_currency"), "booking_date", "orig_currency", "counterparty_name", "statement_format"), on="bank_txn_id", how="left")
             .join(pdf_idx, on=["entity", "num_norm"], how="left")
             .join(detail_tok, left_on="num_norm", right_on="tok", how="left")
             .join(detail_tok.rename({"detail_file": "detail_digits"}), left_on="num_digits", right_on="tok", how="left")
             .join(ra_tok, left_on="num_norm", right_on="tok", how="left")
             .join(ra_tok.rename({"remittance": "remittance_digits"}), left_on="num_digits", right_on="tok", how="left")
             .with_columns(
                 pl.col("text_norm").str.contains(pl.col("num_norm"), literal=True).fill_null(False).alias("text_strict"),
                 pl.when(pl.col("num_digits").is_not_null()).then(pl.col("text_norm").str.contains(pl.col("num_digits"), literal=True)).otherwise(False).fill_null(False).alias("text_digits"),
                 (pl.col("detail_file").fill_null(False) | pl.col("detail_digits").fill_null(False)).alias("detail_file"),
                 (pl.col("remittance").fill_null(False) | pl.col("remittance_digits").fill_null(False)).alias("remittance"),
                 pl.col("pdf").fill_null(False),
                 (pl.col("currency") != pl.col("txn_currency")).alias("cross_currency"),
                 pl.when(pl.col("name10").str.len_chars() >= 6).then(pl.col("text_norm").str.contains(pl.col("name10"), literal=True)).otherwise(False).fill_null(False).alias("name_in_text"),
                 pl.when(pl.col("item_type").is_in(["ARC", "APC"])).then(-pl.col("amount")).otherwise(pl.col("amount")).alias("signed_amount")))
    missing_items = int(pairs["document_number"].is_null().sum())
    print(f"pares cuyo item no está en las tablas de la fase: {missing_items:,}", file=sys.stderr)

    per_txn = pairs.group_by("bank_txn_id").agg(
        pl.col("segment").first(), pl.len().alias("items"),
        pl.col("text_strict").all().alias("all_text_strict"), pl.col("text_strict").any().alias("any_text_strict"),
        (pl.col("text_strict") | pl.col("text_digits")).all().alias("all_text_loose"),
        pl.col("detail_file").all().alias("all_detail"), pl.col("remittance").all().alias("all_remittance"),
        pl.col("pdf").any().alias("any_pdf"), pl.col("cross_currency").any().alias("cross_currency"),
        pl.col("orig_currency").first().is_not_null().alias("has_orig_currency"),
        pl.col("counterparty_name").first().is_not_null().alias("has_counterparty"),
        ((pl.col("signed_amount").sum() - pl.col("abs_amount").first()).abs() <= 0.011).alias("sum_eq_amount"),
        pl.col("name_in_text").any().alias("name_in_text"),
        pl.col("currency").n_unique().alias("ccy_in_items"),
        pl.col("abs_amount").first(), pl.col("txn_currency").first(), pl.col("entity").first(), pl.col("booking_date").first(),
        pl.col("item_type").first())
    per_txn = per_txn.with_columns((pl.col("sum_eq_amount") & (pl.col("ccy_in_items") == 1) & ~pl.col("cross_currency")).alias("amount_exact"))

    # candidates for single-item lines: invoices of the same entity/currency/total issued in the 400 days before booking
    single = per_txn.filter((pl.col("items") == 1) & pl.col("item_type").is_in(["ARI", "API"]))
    inv = it.filter(pl.col("item_type").is_in(["ARI", "API"])).select("entity", "currency", "total_amount", "issue_date", "item_type")
    cand = (single.select("bank_txn_id", "segment", "entity", pl.col("txn_currency").alias("currency"), pl.col("abs_amount").alias("total_amount"), "booking_date", "item_type")
            .join(inv, on=["entity", "currency", "total_amount", "item_type"], how="left")
            .filter((pl.col("issue_date") <= pl.col("booking_date")) & (pl.col("issue_date") > pl.col("booking_date") - pl.duration(days=400)))
            .group_by("bank_txn_id").agg(pl.len().alias("candidates")))
    single = single.join(cand, on="bank_txn_id", how="left").with_columns(pl.col("candidates").fill_null(0))
    cand_seg = single.group_by("segment").agg(pl.len().alias("single_item_txns"),
                                              (100 * (pl.col("candidates") == 1).mean()).round(1).alias("pct_1_candidate"),
                                              (100 * (pl.col("candidates").is_between(2, 5)).mean()).round(1).alias("pct_2_5"),
                                              (100 * (pl.col("candidates") > 5).mean()).round(1).alias("pct_gt5"),
                                              (100 * (pl.col("candidates") == 0).mean()).round(1).alias("pct_0"))

    seg = per_txn.group_by("segment").agg(
        pl.len().alias("txns"), pl.col("items").sum().alias("pairs"),
        (100 * pl.col("all_text_strict").mean()).round(1).alias("txt_strict"),
        (100 * pl.col("all_text_loose").mean()).round(1).alias("txt_loose"),
        (100 * pl.col("amount_exact").mean()).round(1).alias("amt_exact"),
        (100 * pl.col("all_detail").mean()).round(1).alias("detail"),
        (100 * pl.col("all_remittance").mean()).round(1).alias("advice"),
        (100 * pl.col("any_pdf").mean()).round(1).alias("pdf"),
        (100 * pl.col("cross_currency").mean()).round(1).alias("fx"),
        (100 * pl.col("has_counterparty").mean()).round(1).alias("cpty"),
        (100 * pl.col("name_in_text").mean()).round(1).alias("name"),
        (100 * (pl.col("name_in_text") & pl.col("amount_exact")).mean()).round(1).alias("name_amt"),
        (100 * (~pl.col("all_text_loose") & ~pl.col("all_detail") & ~pl.col("all_remittance") & ~pl.col("amount_exact")).mean()).round(1).alias("none"),
    ).sort("txns", descending=True)
    pair_seg = pairs.group_by("segment").agg(
        (100 * pl.col("text_strict").mean()).round(1).alias("pair_txt_strict"),
        (100 * (pl.col("text_strict") | pl.col("text_digits")).mean()).round(1).alias("pair_txt_loose"),
        (100 * pl.col("detail_file").mean()).round(1).alias("pair_detail"),
        (100 * pl.col("remittance").mean()).round(1).alias("pair_advice"),
        (100 * pl.col("pdf").mean()).round(1).alias("pair_pdf"))
    seg = seg.join(pair_seg, on="segment").join(cand_seg, on="segment", how="left")

    section(f"{phase}: por segmento, % de movimientos cuyos items se encuentran en cada fuente (todas sus partidas)")
    print("Columnas: txt_strict = número impreso en el texto del banco · txt_loose = o sus dígitos sin prefijo · amt_exact = |importe| = suma de partidas, misma divisa · "
          "detail = en fichero de remesa/tarjeta/cheque/pago · advice = en algún aviso de remesa · pdf = alguna partida tiene PDF · fx = partida en otra divisa · "
          "cpty = counterparty_name (camt) · name = los 10 primeros caracteres del nombre del tercero están en el texto · name_amt = nombre y importe exacto · none = ni texto, ni importe exacto, ni fichero, ni aviso\n")
    print(md_table(seg.select("segment", "txns", "pairs", "txt_strict", "txt_loose", "amt_exact", "name", "name_amt", "detail", "advice", "pdf", "fx", "cpty", "none")))
    section(f"{phase}: por segmento, % de pares")
    print(md_table(seg.select("segment", "pairs", "pair_txt_strict", "pair_txt_loose", "pair_detail", "pair_advice", "pair_pdf")))
    section(f"{phase}: candidatos por importe para movimientos de una sola partida (facturas de la misma sociedad, divisa e importe emitidas en los 400 días anteriores)")
    print(md_table(seg.filter(pl.col("single_item_txns").is_not_null()).select("segment", "single_item_txns", "pct_1_candidate", "pct_2_5", "pct_gt5", "pct_0")))

    section(f"{phase}: totales")
    tot = per_txn.select((100 * pl.col("all_text_strict").mean()).round(1).alias("txt_strict"), (100 * pl.col("all_text_loose").mean()).round(1).alias("txt_loose"),
                         (100 * pl.col("amount_exact").mean()).round(1).alias("amt_exact"), (100 * pl.col("all_detail").mean()).round(1).alias("detail"),
                         (100 * pl.col("all_remittance").mean()).round(1).alias("advice"), (100 * pl.col("any_pdf").mean()).round(1).alias("pdf"))
    print(md_table(tot))
    ptot = pairs.select((100 * pl.col("text_strict").mean()).round(1).alias("pair_txt_strict"), (100 * (pl.col("text_strict") | pl.col("text_digits")).mean()).round(1).alias("pair_txt_loose"),
                        (100 * pl.col("detail_file").mean()).round(1).alias("pair_detail"), (100 * pl.col("remittance").mean()).round(1).alias("pair_advice"), (100 * pl.col("pdf").mean()).round(1).alias("pair_pdf"))
    print(md_table(ptot))
    write_json(f"03_sources_{phase}", {"segments": seg.to_dicts(), "txn_totals": tot.to_dicts()[0], "pair_totals": ptot.to_dicts()[0], "missing_items": missing_items})


if __name__ == "__main__":
    main()

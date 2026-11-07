"""FINAL has no golden: compare its run with the last LIVE run and warn about whatever moved. It decides nothing.

    cd backend && uv run python ../scripts/final_check.py ../runs/final-1 [--ref ../runs/live-parties-f]

Shares are in percentage points; a gap above 3 is a warning. Rows per bank line and the mean amount, which are not
shares, warn at 3 % of their value. An entity the reference does not have is compared with the reference's whole.
Hard checks, that do not depend on LIVE: validate, coverage, size, an FX rate for every currency of the phase, every
entity and bank with some line past a fallback, and no file of masters_final/ shorter than the master it replaces.
A bank new to the category table is amber, and red from 90 % of its fallback debits in BANK_FEES: its codes are not
being read. Exit code 1 if anything warns or a hard check fails.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import polars as pl

from closebooks.categories import load_codes
from closebooks.evaluate import validate_file
from closebooks.load import load_masters, short_masters

THRESHOLD = 3.0
MAX_CSV_BYTES = 60_000_000
FALLBACK = "FALLBACK-UNIDENTIFIED"
RED, AMBER, GREEN, END = "\033[31m", "\033[33m", "\033[32m", "\033[0m"
FEES_RED = 90.0  # a new bank above this share of BANK_FEES: its codes are not being read
SCHEMA = {"bankTxnId": pl.String, "amountCents": pl.Int64, "currency": pl.String, "rule": pl.String,
          "category": pl.String}


def _shares(counts: dict[str, int], total: int) -> dict[str, float]:
    return {k: 100 * n / total for k, n in counts.items()}


def _profile(run: Path) -> dict:
    meta = json.loads((run / "run.json").read_text())
    rows = pl.read_ndjson(io.BytesIO(gzip.decompress((run / "explanations.jsonl.gz").read_bytes())), schema=SCHEMA)
    bank = pl.read_csv(Path(meta["dataDir"]) / "bank_transactions.csv.gz", columns=["bank_txn_id", "entity", "bank"],
                       infer_schema_length=0)
    per_entity = bank.group_by("entity").len().join(
        rows.filter(pl.col("rule") == FALLBACK).join(bank, left_on="bankTxnId", right_on="bank_txn_id")
        .group_by("entity").len().rename({"len": "fallback"}), on="entity", how="left").with_columns(
        (100 * pl.col("fallback").fill_null(0) / pl.col("len")).alias("share"))
    families = Counter()
    for rule, n in meta["byRule"].items():
        families[rule.split("-")[0]] += n
    amounts = rows.filter(pl.col("amountCents").is_not_null())
    return {"meta": meta, "rows": meta["rows"], "bank_ids": bank["bank_txn_id"], "bank": bank,
            "rule_rows": rows.select("bankTxnId", "rule", "category"),
            "by_rule": _shares(meta["byRule"], meta["rows"]), "by_family": _shares(families, meta["rows"]),
            "by_exception": _shares(meta.get("byException", {}), meta["rows"]),
            "unidentified": dict(per_entity.select("entity", "share").iter_rows()),
            "unidentified_all": 100 * meta["byRule"].get(FALLBACK, 0) / meta["txns"],
            "row_ids": rows["bankTxnId"], "amounts": amounts.select("amountCents", "currency")}


def _without_rate(folder: Path, masters: dict) -> dict[str, int]:
    """Lines per currency of the phase, in bank lines or items, that the FX file does not have."""
    known = set(masters["fx_rates"]["currency"]) | {"EUR"}
    found: Counter = Counter()
    bank = pl.read_csv(folder / "bank_transactions.csv.gz", columns=["currency", "orig_currency"],
                       infer_schema_length=0)
    for column in bank.get_columns():
        found.update(dict(column.drop_nulls().value_counts().iter_rows()))
    for name in ("ar_invoices", "ap_invoices", "credit_notes", "open_items_at_start"):
        path = folder / f"{name}.csv.gz"
        if path.exists():
            found.update(dict(pl.read_csv(path, columns=["currency"], infer_schema_length=0)["currency"]
                              .drop_nulls().value_counts().iter_rows()))
    return {c: n for c, n in sorted(found.items()) if c not in known}


def _only_fallback(profile: dict, column: str) -> list[str]:
    """Entities or banks where no line got past a fallback: the rules may depend on a name they do not know."""
    rows = profile["rule_rows"].join(profile["bank"], left_on="bankTxnId", right_on="bank_txn_id")
    settled = rows.filter(~pl.col("rule").str.starts_with("FALLBACK-"))[column].unique().to_list()
    return sorted(set(profile["bank"][column].drop_nulls()) - set(settled))


def _banks_out_of_table(profile: dict) -> dict[str, tuple[int, float]]:
    """Banks the category table has never seen, with what became of their debits with no match. A share of BANK_FEES
    is normal in some known banks (0 to 100 % in LIVE), so only a bank with no history is worth a look."""
    known = {key[0] for key in load_codes()}
    rows = profile["rule_rows"].filter(pl.col("rule") == "FALLBACK-CATEGORY").join(
        profile["bank"], left_on="bankTxnId", right_on="bank_txn_id").group_by("bank").agg(
        pl.len().alias("lines"), (pl.col("category") == "BANK_FEES").sum().alias("fees"))
    return {bank: (lines, 100 * fees / lines) for bank, lines, fees in rows.iter_rows() if bank not in known}


def _hard_checks(run: Path, profile: dict) -> list[tuple[str, bool, str]]:
    meta = profile["meta"]
    missing = set(profile["bank_ids"]) - set(profile["row_ids"])
    masters = load_masters(Path(meta["dataDir"]))
    phase = SimpleNamespace(masters=masters, txns=pl.DataFrame({"bank_txn_id": profile["bank_ids"]}))
    report = validate_file(run / "submission.csv.gz", phase)
    no_rate = _without_rate(Path(meta["dataDir"]), masters)
    entities, banks = _only_fallback(profile, "entity"), _only_fallback(profile, "bank")
    short = short_masters(Path(meta["dataDir"]))
    return [("validate oficial", bool(report["ok"]), "; ".join(map(str, report["errors"][:3])) or "ok"),
            ("toda divisa tiene tipo en FX", not no_rate, str(no_rate) if no_rate else "ok"),
            ("ningún masters_final más corto que el maestro que sustituye", not short,
             "; ".join(f"{file}: {rows} filas frente a {base}" for file, (rows, base) in short.items()) or "ok"),
            ("toda sociedad con filas fuera de FALLBACK", not entities, ", ".join(entities) or "ok"),
            ("todo banco con filas fuera de FALLBACK", not banks, ", ".join(banks) or "ok"),
            ("cobertura de movimientos", not missing, f"{profile['bank_ids'].n_unique() - len(missing)} de "
                                                      f"{profile['bank_ids'].n_unique()}"),
            ("tamaño < 60 MB", meta["csvBytes"] < MAX_CSV_BYTES, f"{meta['csvBytes'] / 1e6:.1f} MB")]


def _mean(amounts: pl.DataFrame, currencies: set[str]) -> float:
    """Over the currencies both runs have: a new one in other units would move it on its own."""
    return amounts.filter(pl.col("currency").is_in(list(currencies)))["amountCents"].abs().mean() or 0.0


def _rows(run: dict, ref: dict) -> list[tuple[str, float, float, str, bool]]:
    """(metric, this run, reference, unit, warns)"""
    found = []
    for title, key in (("regla", "by_rule"), ("familia", "by_family"), ("excepción", "by_exception")):
        for name in sorted(run[key].keys() | ref[key].keys()):
            now, then = run[key].get(name, 0.0), ref[key].get(name, 0.0)
            found.append((f"{title} {name}", now, then, "pp", abs(now - then) > THRESHOLD))
    for entity in sorted(run["unidentified"].keys() | ref["unidentified"].keys()):
        new = entity not in ref["unidentified"]
        now = run["unidentified"].get(entity, 0.0)
        then = ref["unidentified_all"] if new else ref["unidentified"][entity]
        label = f"{FALLBACK} {entity}" + (" (nueva: frente al total)" if new else "")
        found.append((label, now, then, "pp", abs(now - then) > THRESHOLD))
    per_line = run["rows"] / run["meta"]["txns"], ref["rows"] / ref["meta"]["txns"]
    common = set(run["amounts"]["currency"]) & set(ref["amounts"]["currency"])
    means = _mean(run["amounts"], common) / 100, _mean(ref["amounts"], common) / 100
    for label, (now, then) in (("filas por movimiento", per_line), ("importe medio (divisas comunes)", means)):
        found.append((label, now, then, "%", abs(now - then) > THRESHOLD / 100 * then))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", type=Path)
    parser.add_argument("--ref", type=Path, default=Path(__file__).parents[1] / "runs" / "live-parties-f")
    args = parser.parse_args()
    run, ref = _profile(args.run), _profile(args.ref)
    print(f"{args.run.name} ({run['meta']['txns']} movimientos) frente a {args.ref.name} ({ref['meta']['txns']})\n")
    hard = _hard_checks(args.run, run)
    for name, ok, detail in hard:
        print(f"{GREEN if ok else RED}{'OK   ' if ok else 'FALLA'}{END} {name}: {detail}")
    new_banks = _banks_out_of_table(run)
    for bank, (lines, fees) in sorted(new_banks.items()):
        red = fees >= FEES_RED
        print(f"{RED + 'FALLA' if red else AMBER + 'AVISO'}{END} banco nuevo {bank}: {lines} filas de respaldo, "
              f"{fees:.0f} % BANK_FEES")
    print()
    rows = _rows(run, ref)
    print(f"{'':6}{'métrica':<58}{'esta':>10}{'referencia':>12}{'dif.':>9}")
    for name, now, then, _unit, warns in sorted(rows, key=lambda r: (not r[4], r[0])):
        gap = now - then
        print(f"{RED + 'AVISO' if warns else GREEN + 'ok   '}{END} {name:<58}{now:>10.2f}{then:>12.2f}{gap:>+9.2f}")
    warnings = sum(r[4] for r in rows)
    new = set(run["amounts"]["currency"]) - set(ref["amounts"]["currency"])
    print(f"\n{warnings} avisos de {len(rows)} métricas. Divisas nuevas, fuera del importe medio: {sorted(new) or '-'}")
    bad_bank = any(fees >= FEES_RED for _, fees in new_banks.values())
    return 1 if warnings or bad_bank or not all(ok for _, ok, _ in hard) else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""FINAL has no golden: compare its run with the last LIVE run and warn about whatever moved. It decides nothing.

    cd backend && uv run python ../scripts/final_check.py ../runs/final-1 [--ref ../runs/live-parties-f]

Shares are in percentage points; a gap above 3 is a warning. Rows per bank line and the mean amount, which are not
shares, warn at 3 % of their value. An entity the reference does not have is compared with the reference's whole.
Exit code 1 if anything warns or a hard check fails.
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

from closebooks.evaluate import validate_file
from closebooks.load import load_masters

THRESHOLD = 3.0
MAX_CSV_BYTES = 60_000_000
FALLBACK = "FALLBACK-UNIDENTIFIED"
RED, GREEN, END = "\033[31m", "\033[32m", "\033[0m"
SCHEMA = {"bankTxnId": pl.String, "amountCents": pl.Int64, "currency": pl.String, "rule": pl.String}


def _shares(counts: dict[str, int], total: int) -> dict[str, float]:
    return {k: 100 * n / total for k, n in counts.items()}


def _profile(run: Path) -> dict:
    meta = json.loads((run / "run.json").read_text())
    rows = pl.read_ndjson(io.BytesIO(gzip.decompress((run / "explanations.jsonl.gz").read_bytes())), schema=SCHEMA)
    bank = pl.read_csv(Path(meta["dataDir"]) / "bank_transactions.csv.gz", columns=["bank_txn_id", "entity"],
                       infer_schema_length=0)
    per_entity = bank.group_by("entity").len().join(
        rows.filter(pl.col("rule") == FALLBACK).join(bank, left_on="bankTxnId", right_on="bank_txn_id")
        .group_by("entity").len().rename({"len": "fallback"}), on="entity", how="left").with_columns(
        (100 * pl.col("fallback").fill_null(0) / pl.col("len")).alias("share"))
    families = Counter()
    for rule, n in meta["byRule"].items():
        families[rule.split("-")[0]] += n
    amounts = rows.filter(pl.col("amountCents").is_not_null())
    return {"meta": meta, "rows": meta["rows"], "bank_ids": bank["bank_txn_id"],
            "by_rule": _shares(meta["byRule"], meta["rows"]), "by_family": _shares(families, meta["rows"]),
            "by_exception": _shares(meta.get("byException", {}), meta["rows"]),
            "unidentified": dict(per_entity.select("entity", "share").iter_rows()),
            "unidentified_all": 100 * meta["byRule"].get(FALLBACK, 0) / meta["txns"],
            "row_ids": rows["bankTxnId"], "amounts": amounts.select("amountCents", "currency")}


def _hard_checks(run: Path, profile: dict) -> list[tuple[str, bool, str]]:
    meta = profile["meta"]
    missing = set(profile["bank_ids"]) - set(profile["row_ids"])
    masters = load_masters(Path(meta["dataDir"]))
    phase = SimpleNamespace(masters=masters, txns=pl.DataFrame({"bank_txn_id": profile["bank_ids"]}))
    report = validate_file(run / "submission.csv.gz", phase)
    return [("validate oficial", bool(report["ok"]), "; ".join(map(str, report["errors"][:3])) or "ok"),
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
    print()
    rows = _rows(run, ref)
    print(f"{'':6}{'métrica':<58}{'esta':>10}{'referencia':>12}{'dif.':>9}")
    for name, now, then, _unit, warns in sorted(rows, key=lambda r: (not r[4], r[0])):
        gap = now - then
        print(f"{RED + 'AVISO' if warns else GREEN + 'ok   '}{END} {name:<58}{now:>10.2f}{then:>12.2f}{gap:>+9.2f}")
    warnings = sum(r[4] for r in rows)
    new = set(run["amounts"]["currency"]) - set(ref["amounts"]["currency"])
    print(f"\n{warnings} avisos de {len(rows)} métricas. Divisas nuevas, fuera del importe medio: {sorted(new) or '-'}")
    return 1 if warnings or not all(ok for _, ok, _ in hard) else 0


if __name__ == "__main__":
    raise SystemExit(main())

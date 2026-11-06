"""The official scorer, imported from the package and never copied. Only local scoring relaxes its limits."""
from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from .load import Phase, load_masters
from .paths import SCORER, phase_dir

EXCEPTIONS = ["PARTIAL", "OVERPAYMENT", "SHORT_DISCOUNT", "SHORT_BANK_CHARGES", "SHORT_WITHHOLDING", "SHORT_DISPUTE",
              "DUPLICATE_PAYMENT", "UNIDENTIFIED", "RETURNED", "FX_DIFFERENCE"]
# TRAIN's golden has 5.4 M rows and 325 MB: all three limits block it, the metric is untouched.
RELAXED = {"MAX_UNCOMPRESSED": 2**40, "MAX_DECOMPRESS": 2**40, "MAX_ROWS": 10**9}
OFFICIAL_SHA256 = "1cc74ec1cda3aac6351bf8353cbc38adc81a7b126f9e8c1d75cc5e08bc45fd81"


def _scorer(relaxed: bool) -> ModuleType:
    name = f"_bankrec_score_{'relaxed' if relaxed else 'official'}"
    if name in sys.modules:
        return sys.modules[name]
    if hashlib.sha256(SCORER.read_bytes()).hexdigest() != OFFICIAL_SHA256:
        print(f"warning: {SCORER} differs from the scorer this code was checked with", file=sys.stderr)
    spec = importlib.util.spec_from_file_location(name, SCORER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if relaxed:
        for constant, value in RELAXED.items():
            setattr(module, constant, value)
    return module


def _categories(folder: Path) -> list[str]:
    return load_masters(folder)["categories"]["category"].to_list()


def score_file(submission: Path, phase_name: str) -> dict:
    """Against the golden of a phase that has one. Returns score_submission's dict untouched."""
    folder = phase_dir(phase_name)
    scorer = _scorer(relaxed=True)
    golden = scorer.load_golden(str(folder / "golden_allocations.csv.gz"), str(folder / "bank_transactions.csv.gz"),
                                EXCEPTIONS, _categories(folder))
    return scorer.score_submission(golden, Path(submission).read_bytes(), Path(submission).name)


def validate_file(submission: Path, phase: Phase) -> dict:
    """The upload's validation, official limits included, with no golden: what the server would reject."""
    scorer = _scorer(relaxed=False)
    golden = scorer.Golden()
    golden.exceptions = list(EXCEPTIONS)
    golden.categories = phase.masters["categories"]["category"].to_list()
    golden.txns = {t: ({}, "", "", "unlabelled") for t in phase.txns["bank_txn_id"].to_list()}
    data = Path(submission).read_bytes()
    result = scorer.score_submission(golden, data, Path(submission).name)
    return {"ok": result["ok"], "errors": result["errors"], "rows": result["metrics"].get("rows"),
            "txnsCovered": result["metrics"].get("txns_covered"), "txnsTotal": result["metrics"].get("txns_total")}


def segment_changes(base: dict, now: dict) -> list[tuple[str, int, float, float]]:
    """(segment, n, accuracy before, accuracy now), the ones that drop first."""
    rows = [(seg, info["n"], base.get(seg, {}).get("accuracy", 0.0), info["accuracy"]) for seg, info in now.items()]
    return sorted(rows, key=lambda r: (r[3] - r[2], -r[1]))

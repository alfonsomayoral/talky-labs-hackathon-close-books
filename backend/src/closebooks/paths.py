"""Where a phase lives. db/ and runs/ are outside git; nothing here lists entities, accounts or formats."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DB = ROOT / "db"
RUNS = ROOT / "runs"
PKG = DB / "bankrec-docs-and-masters"
SCORER = PKG / "starter" / "bankrec_score.py"
CATEGORY_CODES = Path(__file__).parent / "data" / "category_codes.csv"


def category_codes_path() -> Path:
    """The table learned from TRAIN; CLOSEBOOKS_CATEGORY_CODES points a run to another one (holdout checks)."""
    return Path(os.environ.get("CLOSEBOOKS_CATEGORY_CODES") or CATEGORY_CODES)


def phase_dir(name: str) -> Path:
    candidates = [PKG / "sample"] if name == "sample" else [DB / name, PKG / name]
    for path in candidates:
        if (path / "bank_transactions.csv.gz").exists():
            return path
    raise FileNotFoundError(f"phase {name!r} not found under {DB}")


def masters_dir(phase: Path) -> Path:
    """FINAL brings its own masters (masters_final/); a phase built or uploaded may bring masters/."""
    for sub in ("masters_final", "masters"):
        if (phase / sub).is_dir():
            return phase / sub
    return PKG / "masters"

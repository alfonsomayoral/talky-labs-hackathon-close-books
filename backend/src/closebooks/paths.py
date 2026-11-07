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


def base_master_path(phase: Path, name: str) -> Path:
    """The master a file of masters_final/ replaces: the phase's own (built or uploaded) or the package's."""
    own = phase / "masters" / name
    return own if own.exists() else PKG / "masters" / name


def master_path(phase: Path, name: str) -> Path:
    """One master file, by its name with extension. File by file: FINAL's masters_final/ may bring only some."""
    final = phase / "masters_final" / name
    return final if final.exists() else base_master_path(phase, name)

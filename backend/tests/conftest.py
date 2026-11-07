from __future__ import annotations

import pytest

from closebooks import paths
from closebooks.load import load_phase
from closebooks.paths import phase_dir


def require_phase(name: str) -> None:
    """The dataset is not in git: tests over real rows only run where db/ exists."""
    try:
        phase_dir(name)
    except FileNotFoundError:
        pytest.skip(f"phase {name} not available")


@pytest.fixture(autouse=True)
def own_pdf_cache(tmp_path, monkeypatch):
    """No test reads or fills the cache of the real runs."""
    monkeypatch.setattr(paths, "RUNS", tmp_path / "runs")


@pytest.fixture(scope="session")
def sample():
    require_phase("sample")
    return load_phase("sample")


@pytest.fixture(scope="session")
def live():
    require_phase("live")
    return load_phase("live")


@pytest.fixture
def phase_factory(tmp_path):
    """A small phase on disk for a rule test: items, bank lines and the text of the detail files."""
    from types import SimpleNamespace

    import polars as pl

    def build(items, txns, files, accounts=(("ES01-PENA-EUR", "ES01"),), customers=()):
        for folder, text in files.items():
            (tmp_path / folder).mkdir(exist_ok=True)
            (tmp_path / folder / "ES01_202505.csv").write_text(text)
        item_defaults = {"item_type": "ARI", "currency": "EUR", "party_id": None, "party_name": None}
        txn_defaults = {"entity": None, "ref1": None, "ref2": None, "end_to_end_id": None, "remittance_info": None}
        return SimpleNamespace(
            dir=tmp_path, name="synthetic",
            items=pl.DataFrame([{**item_defaults, **i} for i in items],
                               schema_overrides={"party_id": pl.String, "party_name": pl.String}),
            txns=pl.DataFrame([{**txn_defaults, **t} for t in txns],
                              schema_overrides={k: pl.String for k in txn_defaults}),
            masters={
                "bank_accounts": pl.DataFrame(
                    accounts, schema={"account_id": pl.String, "entity": pl.String}, orient="row"),
                "customers": pl.DataFrame(
                    customers, schema={"customer_id": pl.String, "sepa_mandate_id": pl.String}, orient="row"),
            })

    return build

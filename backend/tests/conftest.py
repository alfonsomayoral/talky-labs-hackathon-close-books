from __future__ import annotations

import pytest

from closebooks.load import load_phase
from closebooks.paths import phase_dir


def require_phase(name: str) -> None:
    """The dataset is not in git: tests over real rows only run where db/ exists."""
    try:
        phase_dir(name)
    except FileNotFoundError:
        pytest.skip(f"phase {name} not available")


@pytest.fixture(scope="session")
def sample():
    require_phase("sample")
    return load_phase("sample")


@pytest.fixture(scope="session")
def live():
    require_phase("live")
    return load_phase("live")

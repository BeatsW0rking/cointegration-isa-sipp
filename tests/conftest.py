import numpy as np
import pandas as pd
import pytest

from cointisa.config import load_costs, load_research, load_universe
from cointisa.data.store import to_unix_seconds


@pytest.fixture(scope="session")
def costs_cfg():
    return load_costs()


@pytest.fixture(scope="session")
def universe_cfg():
    return load_universe()


@pytest.fixture(scope="session")
def research_cfg():
    return load_research()


@pytest.fixture
def rng():
    return np.random.default_rng(12345)


@pytest.fixture
def synthetic_bars(rng):
    """1000 daily bars of a random walk with plausible high/low."""
    n = 1000
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.003, n)))
    lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.003, n)))
    t = to_unix_seconds(pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC"))
    return pd.DataFrame({"t": t, "o": o, "h": h, "l": lo, "c": c, "v": rng.integers(1e4, 1e6, n)})

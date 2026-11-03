import numpy as np
import pandas as pd

from cointisa.screen.candidates import candidate_groups
from cointisa.screen.sweep import SweepConfig, sweep


def make_panel(rng, n=1400):
    idx = pd.date_range("2019-01-01", periods=n, freq="B", tz="UTC")
    trend = np.cumsum(rng.normal(0, 0.01, n))
    e = np.zeros(n)
    for t in range(1, n):
        e[t] = 0.85 * e[t - 1] + rng.normal(0, 0.01)
    a = np.exp(4 + trend)
    b = np.exp(4 + trend + e)  # cointegrated with a, half-life ~4 bars
    c = np.exp(3 + np.cumsum(rng.normal(0, 0.01, n)))  # independent
    d = np.exp(3 + np.cumsum(rng.normal(0, 0.01, n)))  # independent
    return pd.DataFrame({"A": a, "B": b, "C": c, "D": d}, index=idx)


def test_candidates_cluster_related_pair(rng):
    panel = make_panel(rng)
    groups, clusters = candidate_groups(panel, threshold=0.5, max_size=3)
    assert ("A", "B") in groups
    assert all(len(g) <= 3 for g in groups)


def test_sweep_finds_true_pair_and_rejects_noise(rng):
    panel = make_panel(rng)
    cfg = SweepConfig(formation_bars=504, validation_bars=126, roll_step=252)
    groups = [("A", "B"), ("C", "D"), ("A", "C")]
    res = sweep(panel, groups, cfg)
    assert not res.empty
    ab = res[res["group"] == "A|B"]
    cd = res[res["group"] == "C|D"]
    assert ab["pass_fdr"].mean() > 0.5
    assert ab["persistent"].mean() > 0.5
    assert cd["pass_fdr"].mean() < 0.5
    assert set(res.columns) >= {"p_fdr", "half_life", "hurst", "val_angle_deg", "beta"}

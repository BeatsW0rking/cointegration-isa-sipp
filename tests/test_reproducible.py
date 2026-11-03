"""End-to-end determinism: screen -> selections -> backtest -> bootstrap, twice, byte-identical."""

import hashlib
import json

import numpy as np
import pandas as pd

from cointisa.backtest.engine import BacktestConfig, GroupSelection, run_backtest
from cointisa.costs.model import CostModel
from cointisa.instruments import Instrument
from cointisa.report.bootstrap import monthly_return_ci
from cointisa.screen.candidates import candidate_groups
from cointisa.screen.sweep import SweepConfig, sweep
from cointisa.signals.spread import SpreadModel


def _fixture_panel(seed=7, n=1300):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-01-01", periods=n, freq="B", tz="UTC")
    trend = np.cumsum(rng.normal(0, 0.008, n))
    e = np.zeros(n)
    for t in range(1, n):
        e[t] = 0.85 * e[t - 1] + rng.normal(0, 0.01)
    cols = {
        "LSE:A": 100 * np.exp(trend),
        "LSE:B": 100 * np.exp(trend + e),
        "LSE:C": 50 * np.exp(np.cumsum(rng.normal(0, 0.01, n))),
        "LSE:D": 50 * np.exp(np.cumsum(rng.normal(0, 0.01, n))),
    }
    return pd.DataFrame(cols, index=idx)


def _run_once(costs_cfg) -> str:
    panel = _fixture_panel()
    insts = {
        s: Instrument(
            symbol=s, name=f"{s} S&P 500", currency="GBP", exchange="LSE", type="etf", country="IE"
        )
        for s in panel.columns
    }
    groups, _ = candidate_groups(panel, threshold=0.5, max_size=3)
    scfg = SweepConfig(formation_bars=504, validation_bars=126, roll_step=63)
    res = sweep(panel, groups, scfg, n_jobs=2)
    h = hashlib.sha256()
    h.update(
        pd.util.hash_pandas_object(res.drop(columns=["form_end_time"]), index=False)
        .to_numpy()
        .tobytes()
    )
    sel = []
    logp = np.log(panel)
    for _, r in res[res["pass_fdr"] & res["pass_quality"]].iterrows():
        members = r["group"].split("|")
        beta = tuple(float(x) for x in r["beta"].split(","))
        start = int(r["form_end"])
        form = logp[members].iloc[start - 504 : start].to_numpy()
        sel.append(
            GroupSelection(
                start=start, models=[SpreadModel.fit(members, beta, form, r["half_life"])]
            )
        )
    spreads = pd.DataFrame(0.001, index=panel.index, columns=panel.columns)
    cm = CostModel(costs_cfg, "t212_isa")
    bt = run_backtest(
        panel, sel, cm, insts, spreads, BacktestConfig("B_cheap_leg_only", max_groups=2), 504
    )
    h.update(bt.equity.to_numpy().tobytes())
    ci = monthly_return_ci(
        bt.equity.resample("ME").last().pct_change().dropna().to_numpy(), n_resamples=300, seed=3
    )
    h.update(json.dumps(ci.__dict__, sort_keys=True).encode())
    return h.hexdigest()


def test_pipeline_is_deterministic(costs_cfg):
    assert _run_once(costs_cfg) == _run_once(costs_cfg)

import numpy as np
import pandas as pd

from cointisa.backtest.prepare import build_selections, inverse_etf_map
from cointisa.config import load_research
from cointisa.instruments import Instrument
from cointisa.judge.rules import RulesJudge


def _inst(sym, name, lev=1.0):
    return Instrument(
        symbol=sym, name=name, currency="GBP", exchange="LSE", type="etf", leverage=lev
    )


def test_inverse_map_pairs_same_benchmark():
    insts = {
        "LSE:VUSA": _inst("LSE:VUSA", "Vanguard S&P 500 UCITS ETF"),
        "LSE:XSPS": _inst("LSE:XSPS", "Xtrackers S&P 500 Inverse Daily Swap UCITS ETF", -1.0),
        "LSE:ISF": _inst("LSE:ISF", "iShares Core FTSE 100 UCITS ETF"),
    }
    m = inverse_etf_map(insts)
    assert m == {"LSE:VUSA": "LSE:XSPS"}


def test_build_selections_has_no_lookahead(tmp_path):
    rcfg = load_research()
    n = 800
    idx = pd.date_range("2021-01-04", periods=n, freq="B", tz="UTC")
    rng = np.random.default_rng(0)
    panel = pd.DataFrame(
        {
            "LSE:A": 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))),
            "LSE:B": 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))),
        },
        index=idx,
    )
    insts = {"LSE:A": _inst("LSE:A", "A S&P 500"), "LSE:B": _inst("LSE:B", "B S&P 500")}
    form_end = 504
    roll = rcfg.roll_step_bars["1D"]
    screen = pd.DataFrame(
        [
            {
                "group": "LSE:A|LSE:B",
                "form_end": form_end,
                "form_end_time": idx[form_end - 1],
                "beta": "1.0,-1.0",
                "half_life": 5.0,
                "pass_fdr": True,
                "pass_quality": True,
            },
            {
                "group": "LSE:A|LSE:B",
                "form_end": form_end - roll,
                "form_end_time": idx[form_end - roll - 1],
                "beta": "1.0,-1.0",
                "half_life": 5.0,
                "pass_fdr": True,
                "pass_quality": True,
            },
        ]
    )
    sel = build_selections(screen, panel, insts, RulesJudge(cache_dir=tmp_path), 0.5, rcfg, "1D", 1)
    assert (
        len(sel) == 1 and sel[0].start == form_end
    )  # first tradeable bar is the one after form_end-1
    model = sel[0].models[0]
    # formation statistics must equal those computed on bars strictly before `start`
    logp = np.log(panel[["LSE:A", "LSE:B"]]).to_numpy()
    s = logp[form_end - rcfg.formation_bars["1D"] : form_end] @ np.array(model.beta)
    assert np.isclose(model.mean, s.mean()) and np.isclose(model.std, s.std(ddof=1))
    # a group that only passed at one roll (no stability) is not selected
    sel2 = build_selections(
        screen.iloc[:1], panel, insts, RulesJudge(cache_dir=tmp_path), 0.5, rcfg, "1D", 1
    )
    assert sel2 == []

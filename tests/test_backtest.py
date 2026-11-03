import numpy as np
import pandas as pd
import pytest

from cointisa.backtest.engine import BacktestConfig, GroupSelection, run_backtest
from cointisa.costs.model import CostModel
from cointisa.instruments import Instrument
from cointisa.signals.spread import SpreadModel, cheap_side_weights, target_tilt


def test_tilt_state_machine():
    assert target_tilt(2.5, 0, 2.0, 0.5, 4.0) == 1
    assert target_tilt(-2.5, 0, 2.0, 0.5, 4.0) == -1
    assert target_tilt(1.0, 1, 2.0, 0.5, 4.0) == 1  # hysteresis: stay
    assert target_tilt(0.4, 1, 2.0, 0.5, 4.0) == 0  # exit
    assert target_tilt(4.5, 1, 2.0, 0.5, 4.0) == 0  # stop
    assert target_tilt(1.0, 0, 2.0, 0.5, 4.0) == 0


def test_cheap_side_weights():
    beta = np.array([1.0, -0.8])
    assert np.allclose(cheap_side_weights(beta, 1), [0.0, 1.0])  # spread rich -> second is cheap
    assert np.allclose(cheap_side_weights(beta, -1), [1.0, 0.0])
    assert np.allclose(cheap_side_weights(beta, 0), [0.0, 0.0])


def make_pair_panel(rng, n=800):
    idx = pd.date_range("2021-01-04", periods=n, freq="B", tz="UTC")
    trend = np.cumsum(rng.normal(0, 0.008, n))
    e = np.zeros(n)
    for t in range(1, n):
        e[t] = 0.9 * e[t - 1] + rng.normal(0, 0.01)
    a = 100 * np.exp(trend)
    b = 100 * np.exp(trend + e)
    return pd.DataFrame({"LSE:A": a, "LSE:B": b}, index=idx), e


INSTS = {
    "LSE:A": Instrument(
        symbol="LSE:A", name="A S&P 500", currency="GBP", exchange="LSE", type="etf", country="IE"
    ),
    "LSE:B": Instrument(
        symbol="LSE:B", name="B S&P 500", currency="GBP", exchange="LSE", type="etf", country="IE"
    ),
}


@pytest.mark.parametrize("variant", ["A_basket_rotation", "B_cheap_leg_only"])
@pytest.mark.parametrize("account", ["t212_isa", "hl_sipp"])
def test_backtest_runs_and_accounts_for_costs(rng, costs_cfg, variant, account):
    panel, e = make_pair_panel(rng)
    logp = np.log(panel)
    form = logp.iloc[:400].to_numpy()
    model = SpreadModel.fit(("LSE:A", "LSE:B"), (1.0, -1.0), form, half_life=6.6)
    sel = [GroupSelection(start=400, models=[model])]
    spreads = pd.DataFrame(0.001, index=panel.index, columns=panel.columns)
    cfg = BacktestConfig(variant=variant, max_groups=1, trade_bars=10_000)
    cm = CostModel(costs_cfg, account)
    res = run_backtest(panel, sel, cm, INSTS, spreads, cfg, start_bar=400)
    assert len(res.equity) == 400
    assert res.equity.iloc[0] == pytest.approx(cm.acc.capital_gbp, rel=0.01)
    assert len(res.trades) > 2
    assert res.costs["total"].sum() > 0
    assert set(res.trades["reason"]) & {"entry", "exit", "open"}
    # no shorting ever
    assert (res.trades.groupby("symbol")["qty"].apply(lambda q: q.sum()) >= -1e-9).all()
    if account == "hl_sipp":
        assert (res.trades["qty"] == res.trades["qty"].round()).all()  # whole shares
        assert (res.costs["fixed_fee"] > 0).all()
    assert np.isfinite(res.stats["sharpe"]) or res.stats["n_trades"] == 0


def test_backtest_pair_signal_has_positive_gross_edge(rng, costs_cfg):
    """With a strongly mean-reverting synthetic spread and zero costs, variant B should beat cash."""
    panel, _ = make_pair_panel(rng, n=1500)
    logp = np.log(panel)
    model = SpreadModel.fit(
        ("LSE:A", "LSE:B"), (1.0, -1.0), logp.iloc[:500].to_numpy(), half_life=6.6
    )
    sel = [GroupSelection(start=500, models=[model])]
    spreads = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
    cfg = BacktestConfig(variant="B_cheap_leg_only", max_groups=1, trade_bars=10_000, z_entry=1.5)
    cm = CostModel(costs_cfg, "t212_isa")
    cm.acc = cm.acc.model_copy(update={"slippage_pct": 0.0})
    res = run_backtest(panel, sel, cm, INSTS, spreads, cfg, start_bar=500)
    assert res.stats["n_trades"] > 10
    assert res.stats["total_return"] > 0


# ---- phase 2: long/short variant D ---------------------------------------------------------------


def test_long_short_weights_are_signed_and_hedge_ratio_weighted():
    from cointisa.signals.spread import long_short_weights

    beta = np.array([1.0, -0.8])
    w = long_short_weights(beta, -1)  # spread cheap: long A, short B
    assert np.allclose(w, [1 / 1.8, -0.8 / 1.8])
    w = long_short_weights(beta, 1)  # spread rich: short A, long B
    assert np.allclose(w, [-1 / 1.8, 0.8 / 1.8])
    assert np.allclose(long_short_weights(beta, 0), [0, 0])


def test_variant_d_zero_cost_pair_profits_and_stays_neutral(rng, costs_cfg):
    panel, _ = make_pair_panel(rng, n=1500)
    logp = np.log(panel)
    model = SpreadModel.fit(
        ("LSE:A", "LSE:B"), (1.0, -1.0), logp.iloc[:500].to_numpy(), half_life=6.6
    )
    sel = [GroupSelection(start=500, models=[model])]
    spreads = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
    cm = CostModel(costs_cfg, "ig_spreadbet")
    cm.acc = cm.acc.model_copy(
        update={
            "slippage_pct": 0.0,
            "spread_markup_bps": 0.0,
            "long_financing_markup_pct": None,
            "short_financing_markup_pct": None,
            "borrow_fee_pct": 0.0,
        }
    )
    cfg = BacktestConfig(variant="D_long_short", max_groups=1, trade_bars=10_000, z_entry=1.5)
    res = run_backtest(panel, sel, cm, INSTS, spreads, cfg, start_bar=500)
    assert res.stats["n_trades"] > 10
    assert res.stats["total_return"] > 0
    assert (res.trades["qty"] < 0).any() or (res.trades["side"] == "sell").any()
    # dollar neutral by hedge ratio (beta = 1): long and short notionals match at every entry
    entries = res.trades[res.trades["reason"] == "entry"]
    by_bar = entries.groupby("bar")["notional_gbp"].agg(["min", "max"])
    assert np.allclose(by_bar["min"], by_bar["max"], rtol=0.02)
    assert res.stats["financing_gbp"] == 0.0
    assert res.stats["benchmark_total_return"] == 0.0  # cash benchmark


def test_variant_d_accrues_financing_on_shorting_venue(rng, costs_cfg):
    panel, _ = make_pair_panel(rng, n=900)
    logp = np.log(panel)
    model = SpreadModel.fit(
        ("LSE:A", "LSE:B"), (1.0, -1.0), logp.iloc[:400].to_numpy(), half_life=6.6
    )
    sel = [GroupSelection(start=400, models=[model])]
    spreads = pd.DataFrame(0.001, index=panel.index, columns=panel.columns)
    cm = CostModel(costs_cfg, "t212_cfd")  # charges financing on both legs
    cfg = BacktestConfig(variant="D_long_short", max_groups=1, trade_bars=10_000)
    res = run_backtest(panel, sel, cm, INSTS, spreads, cfg, start_bar=400)
    fin = res.costs[res.costs["financing"] > 0]
    assert len(fin) > 0 and res.stats["financing_gbp"] > 0
    # one bar of carry on gross exposure G at 7%/yr both sides: G * 0.07 / 252
    row = fin.iloc[0]
    held = res.holdings.loc[row["time"]]
    assert row["financing"] > 0 and held["n_tilted"] >= 1


def test_variant_d_refused_on_long_only_account(rng, costs_cfg):
    panel, _ = make_pair_panel(rng, n=600)
    model = SpreadModel.fit(
        ("LSE:A", "LSE:B"), (1.0, -1.0), np.log(panel.iloc[:400]).to_numpy(), 6.6
    )
    spreads = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
    with pytest.raises(ValueError):
        run_backtest(
            panel,
            [GroupSelection(400, [model])],
            CostModel(costs_cfg, "t212_isa"),
            INSTS,
            spreads,
            BacktestConfig(variant="D_long_short"),
            400,
        )

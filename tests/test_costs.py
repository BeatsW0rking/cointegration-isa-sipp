import pytest

from cointisa.costs.model import CostModel, corwin_schultz_spread, tiered_fee
from cointisa.data.store import bars_to_series
from cointisa.instruments import Instrument

ETF_GBP = Instrument(
    symbol="LSE:VUSA",
    name="Vanguard S&P 500",
    currency="GBP",
    exchange="LSE",
    type="etf",
    country="IE",
)
ETF_USD = Instrument(
    symbol="LSE:CSPX",
    name="iShares Core S&P 500",
    currency="USD",
    exchange="LSE",
    type="etf",
    country="IE",
)
UK_STOCK = Instrument(
    symbol="LSE:SHEL", name="Shell", currency="GBX", exchange="LSE", type="stock", country="GB"
)
US_STOCK = Instrument(
    symbol="NASDAQ:AAPL",
    name="Apple",
    currency="USD",
    exchange="NASDAQ",
    type="stock",
    country="US",
)


def test_t212_gbp_etf_round_trip_is_spread_plus_slippage(costs_cfg):
    cm = CostModel(costs_cfg, "t212_isa")
    # 10 bps full spread, 5 bps slippage each way -> 10 + 10 = 20 bps round trip
    assert cm.round_trip_pct(ETF_GBP, 3000, 0.0010) == pytest.approx(0.0020)


def test_t212_fx_fee_applies_to_usd_line(costs_cfg):
    cm = CostModel(costs_cfg, "t212_isa")
    f = cm.fill_cost(ETF_USD, "buy", 3000, 0.0)
    assert f.fx_fee == pytest.approx(3000 * 0.0015)
    assert f.stamp_duty == 0.0


def test_stamp_duty_on_uk_share_buys_only(costs_cfg):
    cm = CostModel(costs_cfg, "t212_isa")
    buy = cm.fill_cost(UK_STOCK, "buy", 2000, 0.0)
    sell = cm.fill_cost(UK_STOCK, "sell", 2000, 0.0)
    assert buy.stamp_duty == pytest.approx(10.0)
    assert sell.stamp_duty == 0.0


def test_ptm_levy_above_threshold(costs_cfg):
    cm = CostModel(costs_cfg, "hl_sipp")
    assert cm.fill_cost(UK_STOCK, "sell", 12000, 0.0).ptm_levy == costs_cfg.taxes.ptm_levy_gbp
    assert cm.fill_cost(UK_STOCK, "sell", 9000, 0.0).ptm_levy == 0.0


def test_hl_fixed_fee_and_frequent_trader(costs_cfg):
    cm = CostModel(costs_cfg, "hl_sipp")
    assert cm.fixed_fee(0) == 6.95
    assert cm.fixed_fee(20) == 3.95
    # 5k clip round trip at HL on a GBP ETF with zero spread: 2 * 6.95 + 2 * slippage
    rt = cm.round_trip_pct(ETF_GBP, 5000, 0.0)
    assert rt == pytest.approx((2 * 6.95 + 2 * 5000 * 0.0005) / 5000)


def test_hl_fx_tiers_marginal(costs_cfg):
    cm = CostModel(costs_cfg, "hl_sipp")
    tiers = cm.acc.fx_fee_tiers
    assert tiered_fee(4000, tiers) == pytest.approx(4000 * 0.0099)
    assert tiered_fee(10000, tiers) == pytest.approx(5000 * 0.0099 + 5000 * 0.0075)
    assert cm.fill_cost(US_STOCK, "buy", 10000, 0.0).fx_fee == pytest.approx(
        5000 * 0.0099 + 5000 * 0.0075
    )


def test_whole_share_rounding(costs_cfg):
    assert CostModel(costs_cfg, "hl_sipp").round_quantity(12.9) == 12.0
    assert CostModel(costs_cfg, "t212_isa").round_quantity(12.9) == 12.9


def test_corwin_schultz_positive_and_bounded(synthetic_bars):
    h = bars_to_series(synthetic_bars, "h")
    lo = bars_to_series(synthetic_bars, "l")
    s = corwin_schultz_spread(h, lo).dropna()
    assert (s >= 0).all()
    assert s.median() < 0.02  # a few bps to <2% for a random walk with 30 bps ranges

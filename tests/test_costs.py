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


# ---- phase 2: shorting venues and fee-free SIPPs ----------------------------------------------


def test_spread_bet_round_trip_and_carry(costs_cfg):
    cm = CostModel(costs_cfg, "ig_spreadbet")
    # UK share: no stamp duty, no PTM; spread = market 10 bps + IG 10 bps; slippage 5 bps/side
    f = cm.fill_cost(UK_STOCK, "buy", 10000, 0.0010)
    assert f.stamp_duty == 0.0 and f.ptm_levy == 0.0 and f.fixed_fee == 0.0
    assert f.half_spread == pytest.approx(10000 * 0.0020 / 2)
    assert cm.round_trip_pct(UK_STOCK, 10000, 0.0010) == pytest.approx(0.0020 + 0.0010)
    # one year of £10k long / £10k short: long pays 7%, short receives 1%, borrow 0.5%
    carry = sum(cm.financing_per_bar(10000, 10000, 252) for _ in range(252))
    assert carry == pytest.approx(10000 * 0.07 - 10000 * 0.01 + 10000 * 0.005, rel=1e-6)


def test_ibkr_commission_minimum_and_stamp_duty(costs_cfg):
    cm = CostModel(costs_cfg, "ibkr_margin")
    small = cm.fill_cost(UK_STOCK, "buy", 1000, 0.0)
    assert small.fixed_fee == pytest.approx(1.0)  # minimum beats 0.05% of £1k
    big = cm.fill_cost(UK_STOCK, "buy", 10000, 0.0)
    assert big.fixed_fee == pytest.approx(5.0)
    assert big.stamp_duty == pytest.approx(50.0)  # real shares still pay SDRT
    carry = sum(cm.financing_per_bar(10000, 10000, 252) for _ in range(252))
    assert carry == pytest.approx(10000 * 0.0075, rel=1e-6)  # borrow fee only at 1x gross


def test_t212_cfd_charges_both_sides(costs_cfg):
    cm = CostModel(costs_cfg, "t212_cfd")
    carry = sum(cm.financing_per_bar(10000, 10000, 252) for _ in range(252))
    assert carry == pytest.approx(2 * 10000 * 0.07, rel=1e-6)
    assert cm.fill_cost(US_STOCK, "buy", 5000, 0.0).fx_fee == 0.0  # FX only on P&L


def test_long_only_accounts_have_no_financing(costs_cfg):
    for acc in ("t212_isa", "hl_sipp", "t212_sipp", "investengine_sipp"):
        assert CostModel(costs_cfg, acc).financing_per_bar(10000, 0, 252) == 0.0
        assert not CostModel(costs_cfg, acc).acc.allow_short


def test_fee_free_sipps_round_trip(costs_cfg):
    t212 = CostModel(costs_cfg, "t212_sipp")
    ie = CostModel(costs_cfg, "investengine_sipp")
    assert t212.round_trip_pct(ETF_USD, 5000, 0.0010) == pytest.approx(0.0010 + 0.0010 + 2 * 0.0015)
    assert ie.round_trip_pct(ETF_USD, 5000, 0.0010) == pytest.approx(0.0010 + 0.0010)

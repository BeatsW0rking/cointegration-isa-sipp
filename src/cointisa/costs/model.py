"""Transaction cost model for a long-only UK retail account.

A fill's cost in GBP = half-spread + slippage + FX fee + stamp duty (buys of UK/IE shares)
+ PTM levy + fixed dealing fee. Platform fees are charged separately per period.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from cointisa.config import AccountCosts, CostsConfig
from cointisa.instruments import Instrument


@dataclass
class FillCost:
    notional_gbp: float
    half_spread: float
    slippage: float
    fx_fee: float
    stamp_duty: float
    ptm_levy: float
    fixed_fee: float
    other: float = 0.0
    components: dict[str, float] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return (
            self.half_spread
            + self.slippage
            + self.fx_fee
            + self.stamp_duty
            + self.ptm_levy
            + self.fixed_fee
            + self.other
        )

    @property
    def total_pct(self) -> float:
        return self.total / self.notional_gbp if self.notional_gbp else 0.0


def tiered_fee(amount: float, tiers) -> float:
    """Marginal tiered percentage fee (HL FX style)."""
    fee, lower = 0.0, 0.0
    for tier in tiers:
        upper = tier.upto_gbp if tier.upto_gbp is not None else float("inf")
        band = max(0.0, min(amount, upper) - lower)
        fee += band * tier.pct
        lower = upper
        if amount <= upper:
            break
    return fee


class CostModel:
    def __init__(self, cfg: CostsConfig, account: str):
        self.cfg = cfg
        self.account_id = account
        self.acc: AccountCosts = cfg.accounts[account]

    # ---- quantities -------------------------------------------------------------------
    def round_quantity(self, qty: float) -> float:
        if self.acc.fractional_shares:
            return float(np.round(qty, 6))
        return float(np.floor(qty))

    def fixed_fee(self, trades_prior_month: int = 0) -> float:
        acc = self.acc
        if (
            acc.commission_fixed_frequent_gbp is not None
            and acc.frequent_trader_threshold is not None
            and trades_prior_month >= acc.frequent_trader_threshold
        ):
            return acc.commission_fixed_frequent_gbp
        return acc.commission_fixed_gbp

    def fx_fee(self, notional_gbp: float, inst: Instrument) -> float:
        if inst.major_currency == self.acc.base_currency:
            return 0.0
        if self.acc.fx_fee_tiers:
            return tiered_fee(notional_gbp, self.acc.fx_fee_tiers)
        return notional_gbp * (self.acc.fx_fee_pct or 0.0)

    # ---- fills ------------------------------------------------------------------------
    def fill_cost(
        self,
        inst: Instrument,
        side: str,
        notional_gbp: float,
        full_spread_pct: float,
        trades_prior_month: int = 0,
    ) -> FillCost:
        side = side.lower()
        assert side in {"buy", "sell"}
        notional = abs(notional_gbp)
        taxes = self.cfg.taxes
        stamp = 0.0
        if side == "buy" and not self.acc.stamp_duty_exempt:
            if inst.uk_stamp_duty:
                stamp = notional * taxes.uk_stamp_duty_pct
            elif inst.irish_stamp_duty:
                stamp = notional * taxes.irish_stamp_duty_pct
        full_spread_pct = full_spread_pct + self.acc.spread_markup_bps / 1e4
        commission = self.fixed_fee(trades_prior_month)
        if self.acc.commission_pct:
            commission += max(notional * self.acc.commission_pct, self.acc.commission_min_gbp)
        other = 0.0
        if side == "sell" and inst.exchange.upper() in {"NYSE", "NASDAQ", "AMEX", "ARCA", "BATS"}:
            other = notional * taxes.us_sec_fee_pct_sell
        is_uk_line = inst.exchange.upper() in {"LSE", "LON", "AIM"}
        ptm = (
            taxes.ptm_levy_gbp if (is_uk_line and notional > taxes.ptm_levy_threshold_gbp) else 0.0
        )
        return FillCost(
            notional_gbp=notional,
            half_spread=notional * full_spread_pct / 2.0,
            slippage=notional * self.acc.slippage_pct,
            fx_fee=0.0 if self.acc.fx_on_pnl_only else self.fx_fee(notional, inst),
            stamp_duty=stamp,
            ptm_levy=0.0 if self.acc.stamp_duty_exempt else ptm,
            fixed_fee=commission,
            other=other,
        )

    # ---- financing (shorting venues) ----------------------------------------------------
    def financing_per_bar(
        self, long_notional_gbp: float, short_notional_gbp: float, bars_per_year: int
    ) -> float:
        """GBP carry charged for holding the given gross exposures for one bar (positive = cost).

        Longs pay (benchmark + markup); shorts receive (benchmark - markup), which can be negative
        when the markup exceeds the benchmark, unless `short_pays_financing` (then they pay
        benchmark + markup). Shorts also pay `borrow_fee_pct` and earn `short_proceeds_rate_pct`.
        Long-only accounts return 0.
        """
        acc = self.acc
        if not acc.allow_short:
            return 0.0
        y = 1.0 / bars_per_year
        cost = 0.0
        if acc.long_financing_markup_pct is not None:
            cost += (
                abs(long_notional_gbp)
                * (acc.benchmark_rate_pct + acc.long_financing_markup_pct)
                * y
            )
        short = abs(short_notional_gbp)
        if acc.short_financing_markup_pct is not None:
            if acc.short_pays_financing:
                cost += short * (acc.benchmark_rate_pct + acc.short_financing_markup_pct) * y
            else:
                cost -= short * (acc.benchmark_rate_pct - acc.short_financing_markup_pct) * y
        cost += short * acc.borrow_fee_pct * y
        cost -= short * acc.short_proceeds_rate_pct * y
        return cost

    def round_trip_pct(
        self, inst: Instrument, notional_gbp: float, full_spread_pct: float
    ) -> float:
        b = self.fill_cost(inst, "buy", notional_gbp, full_spread_pct)
        s = self.fill_cost(inst, "sell", notional_gbp, full_spread_pct)
        return (b.total + s.total) / notional_gbp

    # ---- periodic ---------------------------------------------------------------------
    def platform_fee_for_period(self, avg_holdings_gbp: float, days: float) -> float:
        annual = min(avg_holdings_gbp * self.acc.platform_fee_pct, self.acc.platform_fee_cap_gbp)
        return annual * days / 365.25


# ---- spread estimation ----------------------------------------------------------------
def corwin_schultz_spread(high: pd.Series, low: pd.Series, window: int = 20) -> pd.Series:
    """Corwin & Schultz (2012) high-low spread estimator, rolling mean over `window` bars.

    Returns the estimated *full* proportional spread. Negative estimates are set to zero before
    averaging, as recommended by the authors.
    """
    h, lo = high.astype(float), low.astype(float)
    beta = (np.log(h / lo) ** 2) + (np.log(h.shift(1) / lo.shift(1)) ** 2)
    h2 = pd.concat([h, h.shift(1)], axis=1).max(axis=1)
    l2 = pd.concat([lo, lo.shift(1)], axis=1).min(axis=1)
    gamma = np.log(h2 / l2) ** 2
    k = 3.0 - 2.0 * np.sqrt(2.0)
    alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    spread = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))
    spread = spread.clip(lower=0.0)
    return spread.rolling(window, min_periods=max(2, window // 2)).mean()


def effective_spread(
    est: pd.Series, inst: Instrument, cfg: CostsConfig, calibration_scale: float = 1.0
) -> pd.Series:
    """Apply floor by instrument type and a calibration multiplier from observed live spreads."""
    floor = cfg.spread.floor_bps.get(inst.type, cfg.spread.floor_bps.get("stock", 10)) / 1e4
    return (est * calibration_scale).fillna(floor).clip(lower=floor)

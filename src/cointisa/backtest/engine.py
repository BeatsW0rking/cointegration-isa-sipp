"""Long-only, cost-aware, live-like backtest.

The loop mirrors what the trading bot will do each bar:
  1. at each roll date, refresh the set of eligible groups (statistics known at that date only);
  2. for each open group, update the discrete tilt state from the current z-score;
  3. translate states into target GBP holdings per symbol under the chosen variant;
  4. send the difference as orders, filled at this bar (API account) or next bar (manual account)
     with half-spread, slippage, FX, stamp duty, PTM and fixed fees from the cost model.

Variants
  A_basket_rotation: hold each group equal-weight; when tilted, move the rich side's weight to the
                     cheap side. Always invested in the group (benchmark: equal-weight hold).
  B_cheap_leg_only : hold only the cheap side when tilted, cash otherwise.
  C_inverse_etf_leg: when tilted, hold the cheap side plus an inverse ETF on the rich side's
                     benchmark where one exists (quasi long/short). Requires `inverse_map`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from cointisa.costs.model import CostModel
from cointisa.instruments import Instrument
from cointisa.signals.spread import SpreadModel, cheap_side_weights, target_tilt

log = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    variant: str
    z_entry: float = 2.0
    z_exit: float = 0.5
    z_stop: float = 4.0
    time_stop_half_lives: float = 2.0
    max_groups: int = 5
    trade_bars: int = 126
    min_trade_gbp: float = 50.0  # ignore rebalances smaller than this per symbol
    bars_per_year: int = 252
    min_edge_multiple: float = 0.0  # enter only if |z|*spread_std >= multiple x round-trip cost
    max_group_size: int = 5  # ignore selected groups larger than this


@dataclass
class GroupSelection:
    """Groups eligible from bar `start` onwards; selection used data strictly before `start`."""

    start: int
    models: list[SpreadModel]


@dataclass
class OpenGroup:
    model: SpreadModel
    opened: int
    state: int = 0
    tilted_since: int | None = None
    capital_gbp: float = 0.0


@dataclass
class Trade:
    bar: int
    time: pd.Timestamp
    symbol: str
    side: str
    qty: float
    price: float
    notional_gbp: float
    cost_gbp: float
    group: str
    reason: str


@dataclass
class BacktestResult:
    equity: pd.Series
    trades: pd.DataFrame
    costs: pd.DataFrame
    holdings: pd.DataFrame
    benchmark: pd.Series
    config: BacktestConfig
    account: str
    stats: dict = field(default_factory=dict)


class Book:
    def __init__(self, cash: float):
        self.cash = cash
        self.qty: dict[str, float] = {}
        self.trades: list[Trade] = []
        self.cost_rows: list[dict] = []
        self.trades_this_month = 0
        self.trades_prev_month = 0

    def value(self, prices: pd.Series) -> float:
        return self.cash + sum(q * prices[s] for s, q in self.qty.items() if q)

    def execute(
        self,
        bar,
        time,
        symbol,
        target_gbp,
        price,
        inst,
        cm: CostModel,
        spread_pct,
        group,
        reason,
        min_trade_gbp,
    ):
        cur_gbp = self.qty.get(symbol, 0.0) * price
        delta = target_gbp - cur_gbp
        if abs(delta) < min_trade_gbp:
            return
        qty = cm.round_quantity(abs(delta) / price)
        if qty <= 0:
            return
        side = "buy" if delta > 0 else "sell"
        if side == "sell":
            qty = min(qty, self.qty.get(symbol, 0.0))
            if qty <= 0:
                return
        notional = qty * price
        fc = cm.fill_cost(inst, side, notional, spread_pct, self.trades_prev_month)
        if side == "buy":
            if notional + fc.total > self.cash:
                # scale down to available cash
                notional = max(0.0, self.cash - fc.total)
                qty = cm.round_quantity(notional / price)
                if qty <= 0:
                    return
                notional = qty * price
                fc = cm.fill_cost(inst, side, notional, spread_pct, self.trades_prev_month)
            self.cash -= notional + fc.total
            self.qty[symbol] = self.qty.get(symbol, 0.0) + qty
        else:
            self.cash += notional - fc.total
            self.qty[symbol] = self.qty.get(symbol, 0.0) - qty
            if abs(self.qty[symbol]) < 1e-9:
                self.qty[symbol] = 0.0
        self.trades_this_month += 1
        self.trades.append(
            Trade(bar, time, symbol, side, qty, price, notional, fc.total, group, reason)
        )
        self.cost_rows.append(
            {
                "bar": bar,
                "time": time,
                "symbol": symbol,
                "half_spread": fc.half_spread,
                "slippage": fc.slippage,
                "fx_fee": fc.fx_fee,
                "stamp_duty": fc.stamp_duty,
                "ptm_levy": fc.ptm_levy,
                "fixed_fee": fc.fixed_fee,
                "other": fc.other,
                "total": fc.total,
            }
        )


def _targets_for_group(
    og: OpenGroup, variant: str, inverse_map: dict[str, str] | None, insts: dict[str, Instrument]
) -> dict[str, float]:
    """Target weights (fraction of the group's capital) per symbol for the current state."""
    m = og.model
    beta = np.asarray(m.beta)
    n = len(m.members)
    if variant == "A_basket_rotation":
        if og.state == 0:
            return dict.fromkeys(m.members, 1.0 / n)
        w = cheap_side_weights(beta, og.state)
        return {s: float(x) for s, x in zip(m.members, w, strict=True)}
    if variant == "B_cheap_leg_only":
        w = cheap_side_weights(beta, og.state)
        return {s: float(x) for s, x in zip(m.members, w, strict=True)}
    if variant == "C_inverse_etf_leg":
        if og.state == 0:
            return {}
        cheap_w = cheap_side_weights(beta, og.state)
        rich = (beta > 0) if og.state == 1 else (beta < 0)
        rich_syms = [s for s, r in zip(m.members, rich, strict=True) if r]
        inv = [inverse_map.get(s) for s in rich_syms] if inverse_map else []
        inv = [i for i in inv if i and i in insts]
        if not inv:
            return {}  # no inverse available: stay flat in this variant
        # half the slice long the cheap side, half in inverse ETF(s) of the rich side
        out = {s: 0.5 * float(x) for s, x in zip(m.members, cheap_w, strict=True) if x > 0}
        for i in inv:
            out[i] = out.get(i, 0.0) + 0.5 / len(inv)
        return out
    raise ValueError(variant)


def run_backtest(
    panel: pd.DataFrame,
    selections: list[GroupSelection],
    cm: CostModel,
    insts: dict[str, Instrument],
    spreads: pd.DataFrame,
    cfg: BacktestConfig,
    start_bar: int,
    inverse_map: dict[str, str] | None = None,
    month_index: pd.Series | None = None,
) -> BacktestResult:
    """Run one variant for one account over panel[start_bar:]. `spreads` is a (bars x symbols)
    frame of estimated full proportional spreads aligned to `panel`."""
    logp = np.log(panel)
    capital = cm.acc.capital_gbp
    book = Book(capital)
    bench = Book(capital)  # equal-weight hold of every group ever selected, rebalanced on selection
    open_groups: dict[str, OpenGroup] = {}
    sel_by_start = {s.start: s for s in selections}
    fill_delay = cm.acc.fill_delay_bars
    pending: list[tuple] = []  # (symbol, target_gbp, inst, group, reason)
    equity, bench_eq, hold_rows = [], [], []
    if month_index is None:
        month_index = pd.Series(panel.index.tz_convert(None).to_period("M"), index=panel.index)
    months = month_index.to_numpy()
    last_month = None
    n = len(panel)
    bench_members: set[str] = set()

    valuation = panel.ffill()  # last known price for marking positions when a bar is missing
    for t in range(start_bar, n):
        prices = panel.iloc[t]
        marks = valuation.iloc[t]
        time = panel.index[t]
        if last_month is not None and months[t] != last_month:
            book.trades_prev_month, book.trades_this_month = book.trades_this_month, 0
        last_month = months[t]

        # 1. fills queued from the previous bar (manual account)
        if pending:
            for sym, target_gbp, inst, group, reason in pending:
                p = prices[sym]
                if np.isfinite(p):
                    book.execute(
                        t,
                        time,
                        sym,
                        target_gbp,
                        p,
                        inst,
                        cm,
                        spreads.iat[t, spreads.columns.get_loc(sym)],
                        group,
                        reason,
                        cfg.min_trade_gbp,
                    )
            pending = []

        orders: list[tuple] = []

        # 2. refresh selection
        if t in sel_by_start:
            fresh = sel_by_start[t].models
            fresh_keys = {"|".join(m.members) for m in fresh}
            # close groups that dropped out and are flat; keep tilted ones until they revert
            for key in list(open_groups):
                og = open_groups[key]
                if key not in fresh_keys and og.state == 0:
                    for s in og.model.members:
                        orders.append((s, 0.0, insts[s], key, "deselected"))
                    del open_groups[key]
            equity_now = book.value(marks)
            for m in fresh:
                key = "|".join(m.members)
                if len(m.members) > cfg.max_group_size:
                    continue
                if key in open_groups or len(open_groups) >= cfg.max_groups:
                    continue
                if any(not np.isfinite(prices[s]) for s in m.members):
                    continue
                open_groups[key] = OpenGroup(
                    model=m, opened=t, capital_gbp=equity_now / cfg.max_groups
                )
                bench_members.update(m.members)
            # benchmark: equal-weight across all members ever selected
            if bench_members:
                bv = bench.value(marks)
                for s in bench_members:
                    if np.isfinite(prices[s]):
                        bench.execute(
                            t,
                            time,
                            s,
                            bv / len(bench_members),
                            prices[s],
                            insts[s],
                            cm,
                            spreads.iat[t, spreads.columns.get_loc(s)],
                            "benchmark",
                            "rebalance",
                            cfg.min_trade_gbp,
                        )

        # 3. update states and targets
        for key, og in list(open_groups.items()):
            lp = np.array([logp.iat[t, logp.columns.get_loc(s)] for s in og.model.members])
            if not np.all(np.isfinite(lp)):
                continue
            z = float(og.model.z(lp))
            new_state = target_tilt(z, og.state, cfg.z_entry, cfg.z_exit, cfg.z_stop)
            reason = None
            if (
                og.tilted_since is not None
                and t - og.tilted_since >= cfg.time_stop_half_lives * max(og.model.half_life, 1)
            ):
                new_state, reason = 0, "time_stop"
            if t - og.opened >= cfg.trade_bars and new_state == 0:
                reason = reason or "window_end"
            if new_state != 0 and og.state == 0 and cfg.min_edge_multiple > 0:
                # cost-aware entry: expected log-price gap must cover the round trip
                probe = OpenGroup(model=og.model, opened=og.opened, state=new_state)
                tgt = _targets_for_group(probe, cfg.variant, inverse_map, insts)
                buys = [s for s, w in tgt.items() if w > 0]
                if buys:
                    slice_gbp = og.capital_gbp * max(tgt.values())
                    cost = float(
                        np.mean(
                            [
                                cm.round_trip_pct(
                                    insts[s],
                                    max(slice_gbp, 1.0),
                                    spreads.iat[t, spreads.columns.get_loc(s)],
                                )
                                for s in buys
                            ]
                        )
                    )
                    if abs(z) * og.model.std < cfg.min_edge_multiple * cost:
                        new_state = 0
            if new_state != og.state:
                if new_state != 0:
                    og.tilted_since = t
                    reason = reason or "entry"
                else:
                    og.tilted_since = None
                    reason = reason or ("stop" if abs(z) >= cfg.z_stop else "exit")
                og.state = new_state
                targets = _targets_for_group(og, cfg.variant, inverse_map, insts)
                syms = set(og.model.members) | set(targets)
                for s in syms:
                    orders.append((s, og.capital_gbp * targets.get(s, 0.0), insts[s], key, reason))
            elif og.state == 0 and cfg.variant == "A_basket_rotation" and og.opened == t:
                targets = _targets_for_group(og, cfg.variant, inverse_map, insts)
                for s, w in targets.items():
                    orders.append((s, og.capital_gbp * w, insts[s], key, "open"))
            if reason == "window_end" and og.state == 0:
                for s in og.model.members:
                    orders.append((s, 0.0, insts[s], key, "window_end"))
                del open_groups[key]

        # 4. route orders
        if orders:
            if fill_delay == 0:
                for sym, target_gbp, inst, group, reason in orders:
                    p = prices[sym]
                    if np.isfinite(p):
                        book.execute(
                            t,
                            time,
                            sym,
                            target_gbp,
                            p,
                            inst,
                            cm,
                            spreads.iat[t, spreads.columns.get_loc(sym)],
                            group,
                            reason,
                            cfg.min_trade_gbp,
                        )
            else:
                pending.extend(orders)

        equity.append(book.value(marks))
        bench_eq.append(bench.value(marks))
        hold_rows.append(
            {
                "time": time,
                "cash": book.cash,
                "n_groups": len(open_groups),
                "n_tilted": sum(1 for g in open_groups.values() if g.state != 0),
            }
        )

    idx = panel.index[start_bar:]
    eq = pd.Series(equity, index=idx, name="equity")
    bm = pd.Series(bench_eq, index=idx, name="benchmark")
    trades = pd.DataFrame([t.__dict__ for t in book.trades])
    costs = pd.DataFrame(book.cost_rows)
    res = BacktestResult(
        eq, trades, costs, pd.DataFrame(hold_rows).set_index("time"), bm, cfg, cm.account_id
    )
    res.stats = summarize(res, cfg.bars_per_year)
    return res


def monthly_returns(equity: pd.Series) -> pd.Series:
    m = equity.resample("ME").last()
    return m.pct_change().dropna()


def summarize(res: BacktestResult, bars_per_year: int) -> dict:
    eq = res.equity
    rets = eq.pct_change().dropna()
    years = len(eq) / bars_per_year
    total = eq.iloc[-1] / eq.iloc[0] - 1
    cagr = (1 + total) ** (1 / years) - 1 if years > 0 else np.nan
    vol = rets.std() * np.sqrt(bars_per_year)
    sharpe = (rets.mean() / rets.std() * np.sqrt(bars_per_year)) if rets.std() > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    mr = monthly_returns(eq)
    bm = res.benchmark.pct_change().dropna()
    if len(bm) == len(rets) and bm.std() > 0:
        beta = np.cov(rets, bm)[0, 1] / bm.var()
        alpha_ann = (rets.mean() - beta * bm.mean()) * bars_per_year
    else:
        beta, alpha_ann = np.nan, np.nan
    return {
        "total_return": float(total),
        "cagr": float(cagr),
        "ann_vol": float(vol),
        "sharpe": float(sharpe),
        "max_drawdown": float(dd),
        "monthly_mean": float(mr.mean()) if len(mr) else np.nan,
        "monthly_std": float(mr.std()) if len(mr) else np.nan,
        "n_months": int(len(mr)),
        "n_trades": int(len(res.trades)),
        "total_costs_gbp": float(res.costs["total"].sum()) if len(res.costs) else 0.0,
        "beta_vs_benchmark": float(beta),
        "alpha_ann_vs_benchmark": float(alpha_ann),
        "benchmark_total_return": float(res.benchmark.iloc[-1] / res.benchmark.iloc[0] - 1),
    }

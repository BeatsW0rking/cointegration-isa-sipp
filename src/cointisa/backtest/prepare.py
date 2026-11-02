"""Glue between screening output and the backtest engine: selections without look-ahead,
spread-estimate panels, and the inverse-ETF map for variant C."""

from __future__ import annotations

import numpy as np
import pandas as pd

from cointisa.backtest.engine import GroupSelection
from cointisa.config import CostsConfig, ResearchConfig
from cointisa.costs.model import corwin_schultz_spread, effective_spread
from cointisa.data.panel import load_close_panel
from cointisa.instruments import Instrument
from cointisa.judge.base import PlausibilityJudge
from cointisa.judge.rules import benchmark_key
from cointisa.signals.spread import SpreadModel


def inverse_etf_map(insts: dict[str, Instrument]) -> dict[str, str]:
    """symbol -> inverse ETF symbol on the same benchmark (-1x only, most liquid name wins)."""
    inverses: dict[str, str] = {}
    for s, i in insts.items():
        if i.leverage == -1.0:
            bk = benchmark_key(i.name)
            if bk and bk not in inverses:
                inverses[bk] = s
    out = {}
    for s, i in insts.items():
        if i.leverage == 1.0:
            bk = benchmark_key(i.name)
            if bk in inverses:
                out[s] = inverses[bk]
    return out


def spread_panel(
    as_of, interval, insts, ccfg: CostsConfig, close_panel: pd.DataFrame
) -> pd.DataFrame:
    """Estimated full proportional spread per bar per symbol (Corwin-Schultz with floors)."""
    hi = load_close_panel(as_of, interval, insts, field="h", min_rows=50)
    lo = load_close_panel(as_of, interval, insts, field="l", min_rows=50)
    cols = {}
    for s in close_panel.columns:
        if s in hi and s in lo:
            est = corwin_schultz_spread(
                hi[s].reindex(close_panel.index), lo[s].reindex(close_panel.index)
            )
        else:
            est = pd.Series(np.nan, index=close_panel.index)
        cols[s] = effective_spread(est, insts[s], ccfg)
    return pd.DataFrame(cols, index=close_panel.index)


def build_selections(
    screen_df: pd.DataFrame,
    panel: pd.DataFrame,
    insts: dict[str, Instrument],
    judge: PlausibilityJudge,
    gate: float,
    rcfg: ResearchConfig,
    interval: str,
    stability_windows: int = 1,
) -> list[GroupSelection]:
    """Selections usable at each formation end: pass FDR + quality at that end, passed at the
    previous `stability_windows` rolls too, and judged plausible. Uses nothing after `form_end`."""
    df = screen_df[screen_df["pass_fdr"] & screen_df["pass_quality"]].copy()
    passed = set(zip(df["group"], df["form_end"], strict=True))
    roll = rcfg.roll_step_bars[interval]
    logp = np.log(panel)
    # map screen's form_end (index into the screening panel) to this panel's index via timestamps
    time_to_pos = {t: i for i, t in enumerate(panel.index)}
    out: dict[int, list[SpreadModel]] = {}
    judged: dict[str, float] = {}
    for _, r in df.iterrows():
        g, end = r["group"], int(r["form_end"])
        if not all((g, end - k * roll) in passed for k in range(1, stability_windows + 1)):
            continue
        members = g.split("|")
        if any(m not in insts or m not in panel.columns for m in members):
            continue
        if g not in judged:
            judged[g] = judge.score([insts[m] for m in members]).prob
        if judged[g] < gate:
            continue
        pos = time_to_pos.get(r["form_end_time"])
        if pos is None:
            continue
        start = pos + 1  # first tradeable bar after the formation window closes
        beta = tuple(float(x) for x in str(r["beta"]).split(","))
        form = logp[members].iloc[start - rcfg.formation_bars[interval] : start].to_numpy()
        if np.isnan(form).any():
            continue
        out.setdefault(start, []).append(
            SpreadModel.fit(members, beta, form, float(r["half_life"]))
        )
    return [GroupSelection(start=s, models=m) for s, m in sorted(out.items())]

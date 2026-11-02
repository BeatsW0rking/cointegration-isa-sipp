"""Edge budget: how much a cointegration signal can earn per trade versus what a round trip costs.

For every pair that passed the in-sample filters, the formation spread standard deviation bounds
the capturable move: entering at |z| = z_entry and exiting at |z| = z_exit captures
(z_entry - z_exit) x sigma in log-price terms per unit of gross exposure, if the spread reverts.
Multiplying by the realised reversion rate (share of entries that exit on reversion rather than
stop or time out) gives the expected gross edge per entry, to be compared with the round-trip cost
at each venue.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from cointisa.config import CostsConfig
from cointisa.costs.model import CostModel
from cointisa.instruments import Instrument


def edge_budget(
    screen_df: pd.DataFrame,
    insts: dict[str, Instrument],
    ccfg: CostsConfig,
    accounts: list[str],
    z_entry: float,
    z_exit: float,
    reversion_rate: float,
    spread_bps_by_type: dict[str, float] | None = None,
    clip_gbp: float = 4000.0,
) -> pd.DataFrame:
    """One row per pair with gross edge per entry and net edge per venue (all in % of gross)."""
    fq = screen_df[screen_df["pass_fdr"] & screen_df["pass_quality"] & (screen_df["size"] == 2)]
    if fq.empty:
        return pd.DataFrame()
    agg = (
        fq.groupby("group")
        .agg(
            windows=("form_end", "size"),
            persist_rate=("persistent", "mean"),
            spread_std=("spread_std", "median"),
            half_life=("half_life", "median"),
        )
        .reset_index()
    )
    agg["gross_edge_pct"] = (z_entry - z_exit) * agg["spread_std"]
    agg["expected_edge_pct"] = agg["gross_edge_pct"] * reversion_rate
    # trades per month if a round trip lasts ~2 half-lives (bars) on daily data
    agg["trades_per_month"] = 21.0 / (2.0 * agg["half_life"]).clip(lower=1)
    spread_bps_by_type = spread_bps_by_type or {"etf": 10.0, "stock": 15.0, "inverse_etf": 15.0}
    for acc in accounts:
        cm = CostModel(ccfg, acc)
        costs = []
        for g in agg["group"]:
            legs = [insts[s] for s in g.split("|") if s in insts]
            if len(legs) != 2:
                costs.append(np.nan)
                continue
            rt = np.mean(
                [
                    cm.round_trip_pct(i, clip_gbp, spread_bps_by_type.get(i.type, 15.0) / 1e4)
                    for i in legs
                ]
            )
            costs.append(rt)
        agg[f"cost_{acc}"] = costs
        agg[f"net_{acc}"] = agg["expected_edge_pct"] - agg[f"cost_{acc}"]
    return agg.sort_values("expected_edge_pct", ascending=False)


def write_edge_budget(
    table: pd.DataFrame, accounts: list[str], out, z_entry, z_exit, reversion_rate
):
    lines = [
        "# Edge budget",
        "",
        f"Entry |z| = {z_entry}, exit |z| = {z_exit}: capturable move per entry is "
        f"{z_entry - z_exit:.1f} x formation spread std, realised on the {reversion_rate:.0%} of "
        "entries that exit on reversion (the rest stop out or time out). Costs are round trips per "
        "leg, averaged, on a £4k clip. All figures in % of gross exposure per entry.",
        "",
    ]
    if table.empty:
        lines.append("No qualifying pairs.")
    else:
        pos = {acc: int((table[f"net_{acc}"] > 0).sum()) for acc in accounts}
        lines.append(
            "Pairs with positive expected net edge: "
            + ", ".join(f"{acc}: {n}/{len(table)}" for acc, n in pos.items())
        )
        lines.append("")
        lines.append(
            f"Median spread std {table['spread_std'].median():.2%}; median gross edge per entry "
            f"{table['gross_edge_pct'].median():.2%}; median expected edge "
            f"{table['expected_edge_pct'].median():.2%}."
        )
        lines.append("")
        show = table.head(25).copy()
        pct_cols = ["spread_std", "gross_edge_pct", "expected_edge_pct"] + [
            c for c in show.columns if c.startswith("cost_") or c.startswith("net_")
        ]
        for c in pct_cols:
            show[c] = show[c].map(lambda v: f"{v:+.2%}" if pd.notna(v) else "")
        show["persist_rate"] = show["persist_rate"].map(lambda v: f"{v:.0%}")
        show["half_life"] = show["half_life"].round(1)
        show["trades_per_month"] = show["trades_per_month"].round(1)
        lines.append(show.to_markdown(index=False))
    out.write_text("\n".join(lines) + "\n")

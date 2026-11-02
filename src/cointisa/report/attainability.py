"""Assemble the attainability report: target vs achieved, per account, variant and timeframe."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from cointisa.backtest.engine import monthly_returns
from cointisa.report.bootstrap import deflated_sharpe, monthly_return_ci


def analyse_equity(
    equity: pd.Series, benchmark: pd.Series, target: float, boot: dict, seed: int, n_trials: int
) -> dict:
    mr = monthly_returns(equity).to_numpy()
    ci = monthly_return_ci(
        mr, target, boot["n_resamples"], boot["mean_block_length_months"], boot["ci"], seed
    )
    bm = monthly_returns(benchmark).to_numpy()
    sr_m = mr.mean() / mr.std(ddof=1) if len(mr) > 2 and mr.std(ddof=1) > 0 else np.nan
    dsr = (
        deflated_sharpe(
            sr_m,
            len(mr),
            n_trials,
            float(stats.skew(mr)),
            float(stats.kurtosis(mr, fisher=False)),
            sharpe_var_trials=1.0 / max(len(mr), 1),
        )
        if np.isfinite(sr_m)
        else np.nan
    )
    return {
        "n_months": ci.n_months,
        "monthly_mean": ci.mean,
        "monthly_mean_ci_lo": ci.mean_ci[0],
        "monthly_mean_ci_hi": ci.mean_ci[1],
        "monthly_geo": ci.geometric_monthly,
        "monthly_geo_ci_lo": ci.geometric_monthly_ci[0],
        "monthly_geo_ci_hi": ci.geometric_monthly_ci[1],
        "p05_month": ci.p05_month,
        "prob_month_ge_target": ci.prob_month_ge_target,
        "prob_month_ge_target_ci_lo": ci.prob_month_ge_target_ci[0],
        "prob_month_ge_target_ci_hi": ci.prob_month_ge_target_ci[1],
        "monthly_sharpe": float(sr_m) if np.isfinite(sr_m) else np.nan,
        "deflated_sharpe_prob": dsr,
        "benchmark_monthly_mean": float(bm.mean()) if len(bm) else np.nan,
        "total_return": float(equity.iloc[-1] / equity.iloc[0] - 1),
        "benchmark_total_return": float(benchmark.iloc[-1] / benchmark.iloc[0] - 1),
    }


def write_report(
    table: pd.DataFrame,
    out: Path,
    target_lo: float,
    target_hi: float,
    run_meta: dict,
    notes: list[str],
) -> None:
    lines = [
        "# Attainability report",
        "",
        f"Run `{run_meta.get('run_id')}` (as of {run_meta.get('as_of')}), config hash "
        f"`{str(run_meta.get('config_hash'))[:12]}`, manifest hash `{str(run_meta.get('manifest_hash'))[:12]}`.",
        "",
        f"**Target:** {target_lo:.0%}-{target_hi:.0%} per month at 95% confidence, net of all costs.",
        "",
        "## Verdict",
        "",
    ]
    if table.empty:
        lines.append("No backtest results available.")
    else:
        best = table.sort_values("monthly_geo_ci_lo", ascending=False).iloc[0]
        met = best["monthly_geo_ci_lo"] >= target_lo
        lines.append(
            f"Best configuration: **{best['account']} / {best['variant']} / {best['interval']}** with a "
            f"geometric mean monthly return of {best['monthly_geo']:+.2%} "
            f"(95% CI {best['monthly_geo_ci_lo']:+.2%} to {best['monthly_geo_ci_hi']:+.2%}) over "
            f"{int(best['n_months'])} months."
        )
        lines.append("")
        lines.append(
            "**Target met at 95% confidence.**"
            if met
            else f"**Target not met.** The lower 95% bound ({best['monthly_geo_ci_lo']:+.2%}/month) is below "
            f"{target_lo:.0%}/month. The table below is the achievable return as measured."
        )
    lines += ["", "## Results (net of costs)", ""]
    cols = [
        "account",
        "variant",
        "interval",
        "n_months",
        "monthly_geo",
        "monthly_geo_ci_lo",
        "monthly_geo_ci_hi",
        "p05_month",
        "prob_month_ge_target",
        "monthly_sharpe",
        "deflated_sharpe_prob",
        "total_return",
        "benchmark_total_return",
        "n_trades",
        "total_costs_gbp",
    ]
    cols = [c for c in cols if c in table.columns]
    t = table[cols].copy()
    pct = [
        "monthly_geo",
        "monthly_geo_ci_lo",
        "monthly_geo_ci_hi",
        "p05_month",
        "prob_month_ge_target",
        "total_return",
        "benchmark_total_return",
    ]
    for c in pct:
        if c in t:
            t[c] = t[c].map(lambda v: f"{v:+.2%}" if pd.notna(v) else "")
    for c in ["monthly_sharpe", "deflated_sharpe_prob"]:
        if c in t:
            t[c] = t[c].map(lambda v: f"{v:.2f}" if pd.notna(v) else "")
    if "total_costs_gbp" in t:
        t["total_costs_gbp"] = t["total_costs_gbp"].map(lambda v: f"£{v:,.0f}")
    lines.append(t.to_markdown(index=False))
    lines += ["", "## Method notes", ""]
    lines += [f"- {n}" for n in notes]
    out.write_text("\n".join(lines) + "\n")

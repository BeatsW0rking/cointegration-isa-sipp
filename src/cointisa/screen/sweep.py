"""Johansen sweep over candidate groups with walk-forward formation/validation windows.

For each formation window end (rolled by `roll_step`), every candidate group is tested on the
formation window. Groups whose FDR-adjusted approximate p-value passes and whose spread half-life
and Hurst are in range are then checked out of sample: the *formation* hedge vector is applied to
the following validation window and that spread must still mean-revert (half-life in range, ADF
rejects at 10%), and the re-estimated vector must stay within `max_angle_deg` of the formation one.
Johansen significance is not required on the short validation window (low power).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from cointisa.stats.fdr import benjamini_hochberg
from cointisa.stats.johansen import hedge_vector_angle_deg, johansen
from cointisa.stats.ou import hurst_exponent, ou_half_life
from cointisa.stats.stationarity import integration_order, spread_adf_p

log = logging.getLogger(__name__)


@dataclass
class SweepConfig:
    formation_bars: int
    validation_bars: int
    roll_step: int
    det_order: int = 0
    max_lag: int = 6
    alpha: float = 0.05
    fdr_q: float = 0.05
    half_life_min: float = 2
    half_life_max: float = 30
    hurst_max: float = 0.5
    max_angle_deg: float = 20
    adf_alpha: float = 0.05
    kpss_alpha: float = 0.05


def _window_ends(n: int, cfg: SweepConfig) -> list[int]:
    """Indices (exclusive) where each formation window ends; validation must fit afterwards."""
    ends = []
    e = cfg.formation_bars
    while e + cfg.validation_bars <= n:
        ends.append(e)
        e += cfg.roll_step
    return ends


def _i1_cache(logp: pd.DataFrame, start: int, end: int, cfg: SweepConfig) -> dict[str, bool]:
    out = {}
    for sym in logp.columns:
        x = logp[sym].to_numpy()[start:end]
        if np.isnan(x).any():
            out[sym] = False
            continue
        try:
            out[sym] = integration_order(x, cfg.adf_alpha, cfg.kpss_alpha).is_i1
        except Exception:  # noqa: BLE001 - statsmodels can fail on degenerate series
            out[sym] = False
    return out


def test_group(logp: np.ndarray, cfg: SweepConfig) -> dict | None:
    if np.isnan(logp).any() or logp.shape[0] < 50:
        return None
    try:
        res = johansen(logp, cfg.det_order, cfg.max_lag, cfg.alpha)
    except Exception as exc:  # noqa: BLE001
        log.debug("johansen failed: %s", exc)
        return None
    spread = res.spread(logp)
    return {
        **res.summary(),
        "half_life": ou_half_life(spread),
        "hurst": hurst_exponent(spread),
        "spread_std": float(np.std(spread)),
    }


def _sweep_window(
    logp: pd.DataFrame, groups: list[tuple[str, ...]], cfg: SweepConfig, end: int
) -> pd.DataFrame | None:
    """Formation tests, FDR, quality and out-of-sample checks for one window end."""
    if end <= cfg.formation_bars:
        return None
    if True:  # noqa: SIM102 - kept as a block to limit the diff against the sequential version
        start = end - cfg.formation_bars
        i1 = _i1_cache(logp, start, end, cfg)
        form_rows = []
        for g in groups:
            if not all(i1.get(s, False) for s in g):
                continue
            x = logp[list(g)].to_numpy()[start:end]
            r = test_group(x, cfg)
            if r is None:
                continue
            r.update({"group": "|".join(g), "size": len(g), "form_start": start, "form_end": end})
            form_rows.append(r)
        if not form_rows:
            return None
        df = pd.DataFrame(form_rows)
        rej, adj = benjamini_hochberg(df["trace_p_approx"].to_numpy(), cfg.fdr_q)
        df["p_fdr"] = adj
        df["pass_fdr"] = rej & (df["rank_trace"] >= 1) & (df["rank_maxeig"] >= 1)
        df["pass_quality"] = df["half_life"].between(cfg.half_life_min, cfg.half_life_max) & (
            df["hurst"] < cfg.hurst_max
        )
        # validation on the following window for candidates that passed
        val_rank, val_angle, val_hl, val_adf = [], [], [], []
        for _, row in df.iterrows():
            if not (row["pass_fdr"] and row["pass_quality"]):
                val_rank.append(np.nan)
                val_angle.append(np.nan)
                val_hl.append(np.nan)
                val_adf.append(np.nan)
                continue
            g = row["group"].split("|")
            xv = logp[g].to_numpy()[end : end + cfg.validation_bars]
            beta_form = np.asarray(row["beta"], float)
            if np.isnan(xv).any():
                val_rank.append(0)
                val_angle.append(np.nan)
                val_hl.append(np.nan)
                val_adf.append(np.nan)
                continue
            spread_oos = xv @ beta_form
            val_hl.append(ou_half_life(spread_oos))
            val_adf.append(spread_adf_p(spread_oos))
            rv = test_group(xv, cfg)
            if rv is None:
                val_rank.append(0)
                val_angle.append(np.nan)
            else:
                val_rank.append(min(rv["rank_trace"], rv["rank_maxeig"]))
                val_angle.append(hedge_vector_angle_deg(beta_form, rv["beta"]))
        df["val_rank"] = val_rank
        df["val_angle_deg"] = val_angle
        df["val_half_life"] = val_hl
        df["val_adf_p"] = val_adf
        df["persistent"] = (
            df["pass_fdr"]
            & df["pass_quality"]
            & df["val_half_life"].between(cfg.half_life_min, 2 * cfg.half_life_max)
            & (df["val_adf_p"] < 0.10)
            & (df["val_angle_deg"] <= cfg.max_angle_deg)
        )
        df["form_end_time"] = logp.index[end - 1]
        log.info(
            "window end=%d: %d tested, %d pass FDR, %d persistent",
            end,
            len(df),
            int(df["pass_fdr"].sum()),
            int(df["persistent"].sum()),
        )
        return df


def sweep(
    panel: pd.DataFrame, groups: list[tuple[str, ...]], cfg: SweepConfig, n_jobs: int = 1
) -> pd.DataFrame:
    """Run `_sweep_window` for every rolling window end, optionally across processes."""
    logp = np.log(panel)
    ends = _window_ends(len(logp), cfg)
    if n_jobs == 1 or len(ends) < 2:
        frames = [_sweep_window(logp, groups, cfg, e) for e in ends]
    else:
        from concurrent.futures import ProcessPoolExecutor

        workers = n_jobs if n_jobs > 0 else None
        with ProcessPoolExecutor(max_workers=workers) as ex:
            frames = list(
                ex.map(
                    _sweep_window, [logp] * len(ends), [groups] * len(ends), [cfg] * len(ends), ends
                )
            )
    rows = [f for f in frames if f is not None and len(f)]
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    out["beta"] = out["beta"].apply(lambda b: ",".join(f"{v:.6f}" for v in b))
    return out

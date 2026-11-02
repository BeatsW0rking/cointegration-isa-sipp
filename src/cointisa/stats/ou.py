"""Spread diagnostics: Ornstein-Uhlenbeck half-life and Hurst exponent."""

from __future__ import annotations

import numpy as np


def ou_half_life(spread: np.ndarray) -> float:
    """Half-life in bars from the AR(1) regression ds_t = a + b*s_{t-1} + e.

    Returns inf if the spread is not mean-reverting (b >= 0).
    """
    s = np.asarray(spread, float)
    s = s[np.isfinite(s)]
    if len(s) < 10:
        return float("inf")
    x, y = s[:-1], np.diff(s)
    xm = x - x.mean()
    denom = (xm**2).sum()
    if denom == 0:
        return float("inf")
    b = (xm * (y - y.mean())).sum() / denom
    if b >= 0:
        return float("inf")
    return float(-np.log(2.0) / np.log1p(b)) if b > -1 else 1.0


def hurst_exponent(series: np.ndarray, min_lag: int = 2, max_lag: int | None = None) -> float:
    """Hurst exponent via variance of lagged differences (log-log slope / 2).

    H < 0.5 mean-reverting, 0.5 random walk, > 0.5 trending.
    """
    s = np.asarray(series, float)
    s = s[np.isfinite(s)]
    n = len(s)
    if n < 20:
        return float("nan")
    max_lag = max_lag or max(min_lag + 1, n // 4)
    lags = np.unique(np.logspace(np.log10(min_lag), np.log10(max_lag), 12).astype(int))
    tau = np.array([np.std(s[lag:] - s[:-lag]) for lag in lags])
    mask = tau > 0
    if mask.sum() < 3:
        return float("nan")
    slope = np.polyfit(np.log(lags[mask]), np.log(tau[mask]), 1)[0]
    return float(slope)


def zscore(spread: np.ndarray, window: int) -> np.ndarray:
    """Rolling z-score using only past and current bars."""
    import pandas as pd

    s = pd.Series(np.asarray(spread, float))
    mu = s.rolling(window, min_periods=window).mean()
    sd = s.rolling(window, min_periods=window).std(ddof=1)
    return ((s - mu) / sd).to_numpy()

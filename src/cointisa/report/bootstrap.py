"""Confidence intervals for monthly returns via the stationary block bootstrap (Politis & Romano 1994)
and the deflated Sharpe ratio (Bailey & Lopez de Prado 2014) for multiple-trial correction."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


def stationary_bootstrap_indices(n: int, mean_block: float, rng: np.random.Generator) -> np.ndarray:
    p = 1.0 / max(mean_block, 1.0)
    idx = np.empty(n, dtype=int)
    idx[0] = rng.integers(n)
    for i in range(1, n):
        if rng.random() < p:
            idx[i] = rng.integers(n)
        else:
            idx[i] = (idx[i - 1] + 1) % n
    return idx


@dataclass
class ReturnCI:
    n_months: int
    mean: float
    mean_ci: tuple[float, float]
    p05_month: float  # 5th percentile monthly return (point estimate)
    p05_ci: tuple[float, float]
    prob_month_ge_target: float
    prob_month_ge_target_ci: tuple[float, float]
    geometric_monthly: float
    geometric_monthly_ci: tuple[float, float]


def monthly_return_ci(
    monthly: np.ndarray,
    target: float = 0.05,
    n_resamples: int = 5000,
    mean_block: float = 3.0,
    ci: float = 0.95,
    seed: int = 0,
) -> ReturnCI:
    r = np.asarray(monthly, float)
    r = r[np.isfinite(r)]
    n = len(r)
    rng = np.random.default_rng(seed)
    if n < 6:
        nan = float("nan")
        return ReturnCI(n, nan, (nan, nan), nan, (nan, nan), nan, (nan, nan), nan, (nan, nan))
    means, p05s, probs, geos = [], [], [], []
    for _ in range(n_resamples):
        s = r[stationary_bootstrap_indices(n, mean_block, rng)]
        means.append(s.mean())
        p05s.append(np.percentile(s, 5))
        probs.append((s >= target).mean())
        geos.append(np.exp(np.mean(np.log1p(np.clip(s, -0.999, None)))) - 1)
    lo, hi = (1 - ci) / 2 * 100, (1 + ci) / 2 * 100
    q = lambda a: (float(np.percentile(a, lo)), float(np.percentile(a, hi)))  # noqa: E731
    return ReturnCI(
        n_months=n,
        mean=float(r.mean()),
        mean_ci=q(means),
        p05_month=float(np.percentile(r, 5)),
        p05_ci=q(p05s),
        prob_month_ge_target=float((r >= target).mean()),
        prob_month_ge_target_ci=q(probs),
        geometric_monthly=float(np.exp(np.mean(np.log1p(np.clip(r, -0.999, None)))) - 1),
        geometric_monthly_ci=q(geos),
    )


def deflated_sharpe(
    sharpe_obs: float, n_obs: int, n_trials: int, skew: float, kurt: float, sharpe_var_trials: float
) -> float:
    """Probability that the observed (per-period) Sharpe exceeds the expected maximum Sharpe from
    `n_trials` unskilled strategies. `kurt` is non-excess kurtosis. Returns a probability in [0,1]."""
    if n_trials < 1 or n_obs < 3:
        return float("nan")
    gamma = 0.5772156649
    sr0 = np.sqrt(max(sharpe_var_trials, 1e-12)) * (
        (1 - gamma) * stats.norm.ppf(1 - 1 / n_trials)
        + gamma * stats.norm.ppf(1 - 1 / (n_trials * np.e))
    )
    denom = np.sqrt(max(1 - skew * sharpe_obs + (kurt - 1) / 4 * sharpe_obs**2, 1e-12))
    z = (sharpe_obs - sr0) * np.sqrt(n_obs - 1) / denom
    return float(stats.norm.cdf(z))

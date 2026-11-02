"""Johansen cointegration test with BIC lag selection and a stable, interpretable output.

Uses statsmodels' coint_johansen. det_order=0 puts a constant in the cointegrating relation
(no deterministic trend), which is the standard choice for log prices of related assets.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
from statsmodels.tsa.api import VAR
from statsmodels.tsa.vector_ar.vecm import coint_johansen

CRIT_INDEX = {0.10: 0, 0.05: 1, 0.01: 2}


@dataclass
class JohansenResult:
    n_obs: int
    n_vars: int
    k_ar_diff: int
    det_order: int
    trace_stat: np.ndarray
    trace_crit: np.ndarray  # (n_vars, 3) at 90/95/99
    maxeig_stat: np.ndarray
    maxeig_crit: np.ndarray
    eigenvalues: np.ndarray
    eigenvectors: np.ndarray  # columns are cointegrating vectors, ordered by eigenvalue
    rank_trace: int
    rank_maxeig: int
    alpha: float
    trace_p_approx: float = field(default=np.nan)

    @property
    def rank(self) -> int:
        """Conservative rank: both tests must agree there is at least one relation."""
        return min(self.rank_trace, self.rank_maxeig)

    @property
    def beta(self) -> np.ndarray:
        """First cointegrating vector, normalised so the first element is 1."""
        v = self.eigenvectors[:, 0]
        return v / v[0]

    def spread(self, log_prices: np.ndarray) -> np.ndarray:
        return np.asarray(log_prices) @ self.beta

    def summary(self) -> dict:
        return {
            "n_obs": self.n_obs,
            "n_vars": self.n_vars,
            "k_ar_diff": self.k_ar_diff,
            "rank_trace": self.rank_trace,
            "rank_maxeig": self.rank_maxeig,
            "trace_stat_r0": float(self.trace_stat[0]),
            "trace_crit95_r0": float(self.trace_crit[0, 1]),
            "trace_crit99_r0": float(self.trace_crit[0, 2]),
            "trace_excess_r0": float(self.trace_stat[0] - self.trace_crit[0, 1]),
            "trace_p_approx": float(self.trace_p_approx),
            "beta": [float(b) for b in self.beta],
        }


def select_lag(y: np.ndarray, max_lag: int) -> int:
    """BIC-optimal VAR lag on levels; k_ar_diff for the VECM is one less (min 0)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sel = VAR(y).select_order(maxlags=max_lag)
    p = int(sel.bic) if sel.bic is not None else 1
    return max(p - 1, 0)


def _rank(stats: np.ndarray, crit: np.ndarray, col: int) -> int:
    r = 0
    for i in range(len(stats)):
        if stats[i] > crit[i, col]:
            r = i + 1
        else:
            break
    return r


def trace_pvalue_approx(stat: float, crit: np.ndarray) -> float:
    """Rough p-value by log-linear interpolation of the 90/95/99 critical values.

    Only used to rank candidates for FDR control; the decision itself uses the critical values.
    Values beyond the 99% point are extrapolated and capped at 1e-6.
    """
    c90, c95, c99 = crit
    ps = np.log([0.10, 0.05, 0.01])
    cs = np.array([c90, c95, c99])
    if stat <= c90:
        # extrapolate downwards towards p=1 using the 90/95 slope
        slope = (ps[1] - ps[0]) / (cs[1] - cs[0])
        p = np.exp(ps[0] + slope * (stat - c90))
        return float(min(p, 1.0))
    if stat >= c99:
        slope = (ps[2] - ps[1]) / (cs[2] - cs[1])
        p = np.exp(ps[2] + slope * (stat - c99))
        return float(max(p, 1e-6))
    return float(np.exp(np.interp(stat, cs, ps)))


def johansen(
    log_prices: np.ndarray, det_order: int = 0, max_lag: int = 6, alpha: float = 0.05
) -> JohansenResult:
    y = np.asarray(log_prices, dtype=float)
    if y.ndim != 2 or y.shape[1] < 2:
        raise ValueError("log_prices must be (n_obs, n_vars>=2)")
    k = select_lag(y, max_lag)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = coint_johansen(y, det_order, k)
    col = CRIT_INDEX[alpha]
    r_trace = _rank(res.lr1, res.cvt, col)
    r_max = _rank(res.lr2, res.cvm, col)
    return JohansenResult(
        n_obs=y.shape[0],
        n_vars=y.shape[1],
        k_ar_diff=k,
        det_order=det_order,
        trace_stat=res.lr1,
        trace_crit=res.cvt,
        maxeig_stat=res.lr2,
        maxeig_crit=res.cvm,
        eigenvalues=np.real(res.eig),
        eigenvectors=np.real(res.evec),
        rank_trace=r_trace,
        rank_maxeig=r_max,
        alpha=alpha,
        trace_p_approx=trace_pvalue_approx(float(res.lr1[0]), res.cvt[0]),
    )


def hedge_vector_angle_deg(b1: np.ndarray, b2: np.ndarray) -> float:
    """Angle between two cointegrating vectors (sign-invariant); 0 = identical direction."""
    a, b = np.asarray(b1, float), np.asarray(b2, float)
    cos = abs(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))

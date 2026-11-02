"""Unit-root checks. Johansen assumes I(1) inputs; I(0) series must be removed first."""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
from statsmodels.tsa.stattools import adfuller, kpss


@dataclass(frozen=True)
class IntegrationResult:
    adf_p_level: float
    kpss_p_level: float
    adf_p_diff: float
    order: int  # 0, 1 or 2 (2 means "not I(1), do not use")

    @property
    def is_i1(self) -> bool:
        return self.order == 1


def integration_order(
    x: np.ndarray, adf_alpha: float = 0.05, kpss_alpha: float = 0.05
) -> IntegrationResult:
    """Classify a series as I(0), I(1) or other.

    I(0): ADF rejects a unit root AND KPSS fails to reject stationarity (both tests agree).
    I(1): otherwise, if first differences pass ADF. When ADF and KPSS both reject on levels the
    series is treated as I(1); a lone 5% ADF rejection is too noisy to discard a random walk.
    """
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        adf_lvl = adfuller(x, regression="c", autolag="AIC")[1]
        kpss_lvl = kpss(x, regression="c", nlags="auto")[1]
        adf_dif = adfuller(np.diff(x), regression="c", autolag="AIC")[1]
    if adf_lvl < adf_alpha and kpss_lvl > kpss_alpha:
        order = 0
    elif adf_dif < adf_alpha:
        order = 1
    else:
        order = 2
    return IntegrationResult(adf_lvl, kpss_lvl, adf_dif, order)


def spread_adf_p(spread: np.ndarray) -> float:
    """ADF p-value (constant, AIC lags) of a spread; used as the out-of-sample reversion check."""
    x = np.asarray(spread, float)
    x = x[np.isfinite(x)]
    if len(x) < 20:
        return 1.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return float(adfuller(x, regression="c", autolag="AIC")[1])

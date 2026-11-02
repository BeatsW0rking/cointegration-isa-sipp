import numpy as np
import pytest

from cointisa.stats.fdr import benjamini_hochberg
from cointisa.stats.johansen import hedge_vector_angle_deg, johansen, trace_pvalue_approx
from cointisa.stats.ou import hurst_exponent, ou_half_life, zscore
from cointisa.stats.stationarity import integration_order


def make_cointegrated(rng, n=1500, beta=(1.0, -0.8, -0.5), phi=0.9, noise=0.02):
    """Common stochastic trend plus stationary AR(1) spread. beta[0]*y1 + beta[1]*y2 + beta[2]*y3 = spread."""
    trend = np.cumsum(rng.normal(0, 0.01, n))
    y2 = trend + np.cumsum(rng.normal(0, 0.01, n))
    y3 = 0.5 * trend + np.cumsum(rng.normal(0, 0.01, n))
    e = np.zeros(n)
    for t in range(1, n):
        e[t] = phi * e[t - 1] + rng.normal(0, noise)
    y1 = -(beta[1] * y2 + beta[2] * y3) / beta[0] + e
    return np.column_stack([y1, y2, y3]), e


def test_johansen_recovers_rank_and_vector(rng):
    y, _ = make_cointegrated(rng)
    res = johansen(y, det_order=0, max_lag=6)
    assert res.rank >= 1
    b = res.beta  # normalised to first element 1 -> expect (1, -0.8, -0.5)
    assert np.allclose(b, [1.0, -0.8, -0.5], atol=0.1)
    assert res.trace_p_approx < 0.01


def test_johansen_rejects_independent_walks(rng):
    y = np.cumsum(rng.normal(0, 0.01, (1500, 3)), axis=0)
    res = johansen(y)
    assert res.rank_trace == 0
    assert res.trace_p_approx > 0.05


def test_pvalue_interpolation_monotone():
    crit = np.array([13.4, 15.5, 19.9])
    ps = [trace_pvalue_approx(s, crit) for s in [5, 13.4, 15.5, 19.9, 40]]
    assert ps == sorted(ps, reverse=True)
    assert (
        ps[1] == pytest.approx(0.10)
        and ps[2] == pytest.approx(0.05)
        and ps[3] == pytest.approx(0.01)
    )


def test_half_life_matches_ar1(rng):
    _, e = make_cointegrated(rng, phi=0.9)
    hl = ou_half_life(e)
    assert 4.0 < hl < 10.0  # theoretical: -ln2/ln(0.9) = 6.6


def test_half_life_inf_for_random_walk(rng):
    rw = np.cumsum(rng.normal(0, 1, 2000))
    assert ou_half_life(rw) > 100 or ou_half_life(rw) == float("inf")


def test_hurst_classification(rng):
    rw = np.cumsum(rng.normal(0, 1, 4000))
    _, e = make_cointegrated(rng, n=4000, phi=0.8)
    assert 0.4 < hurst_exponent(rw) < 0.6
    assert hurst_exponent(e) < 0.4


def test_integration_order(rng):
    rw = np.cumsum(rng.normal(0, 1, 1000))
    _, e = make_cointegrated(rng, phi=0.7)
    assert integration_order(rw).order == 1
    assert integration_order(e).order == 0


def test_bh_fdr():
    p = np.array([0.001, 0.01, 0.02, 0.04, 0.2, 0.5])
    rej, adj = benjamini_hochberg(p, q=0.05)
    # BH: p*n/i = .006 .03 .04 .06 .24 .5 -> first three pass q=0.05
    assert rej.tolist() == [True, True, True, False, False, False]
    assert np.all(np.diff(adj[np.argsort(p)]) >= -1e-12)


def test_zscore_uses_past_only():
    s = np.r_[np.zeros(60), 10.0]
    z = zscore(s, 60)
    assert np.isnan(z[58]) and np.isfinite(z[60]) and z[60] > 5  # window includes the current bar


def test_angle():
    assert hedge_vector_angle_deg([1, -1], [-2, 2]) == pytest.approx(0.0, abs=1e-4)
    assert hedge_vector_angle_deg([1, 0], [0, 1]) == pytest.approx(90.0)

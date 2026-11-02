from cointisa.report.bootstrap import (
    deflated_sharpe,
    monthly_return_ci,
    stationary_bootstrap_indices,
)


def test_bootstrap_indices_cover_range(rng):
    idx = stationary_bootstrap_indices(100, 3.0, rng)
    assert idx.min() >= 0 and idx.max() < 100 and len(idx) == 100


def test_monthly_ci_brackets_truth(rng):
    r = rng.normal(0.01, 0.03, 120)
    ci = monthly_return_ci(r, target=0.05, n_resamples=500, seed=1)
    assert ci.mean_ci[0] < 0.01 < ci.mean_ci[1]
    assert 0 <= ci.prob_month_ge_target <= 1
    assert ci.geometric_monthly < ci.mean  # volatility drag


def test_deflated_sharpe_penalises_many_trials():
    p1 = deflated_sharpe(0.3, 60, 1, 0.0, 3.0, 1.0 / 60)
    p100 = deflated_sharpe(0.3, 60, 100, 0.0, 3.0, 1.0 / 60)
    assert p1 > p100

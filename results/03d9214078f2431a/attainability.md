# Attainability report

Run `03d9214078f2431a` (as of 2026-10-31), config hash `ea992e15379e`, manifest hash `c070f83e2417`.

**Target:** 5%-20% per month at 95% confidence, net of all costs.

## Verdict

Best configuration: **t212_isa / C_inverse_etf_leg / 1D** with a geometric mean monthly return of -0.08% (95% CI -0.16% to +0.01%) over 93 months.

**Target not met.** The lower 95% bound (-0.16%/month) is below 5%/month. The table below is the achievable return as measured.

## Results (net of costs)

| account   | variant           | interval   |   n_months | monthly_geo   | monthly_geo_ci_lo   | monthly_geo_ci_hi   | p05_month   | prob_month_ge_target   |   monthly_sharpe |   deflated_sharpe_prob | total_return   | benchmark_total_return   |   n_trades | total_costs_gbp   |
|:----------|:------------------|:-----------|-----------:|:--------------|:--------------------|:--------------------|:------------|:-----------------------|-----------------:|-----------------------:|:---------------|:-------------------------|-----------:|:------------------|
| hl_sipp   | A_basket_rotation | 1D         |         93 | -0.50%        | -1.12%              | +0.16%              | -5.34%      | +5.38%                 |            -0.14 |                   0    | -36.57%        | +102.96%                 |       2146 | £78,341           |
| hl_sipp   | B_cheap_leg_only  | 1D         |         93 | -0.46%        | -0.84%              | -0.11%              | -3.65%      | +1.08%                 |            -0.24 |                   0    | -34.46%        | +102.96%                 |        822 | £49,041           |
| hl_sipp   | C_inverse_etf_leg | 1D         |         93 | -0.13%        | -0.22%              | -0.04%              | -1.03%      | +0.00%                 |            -0.24 |                   0    | -11.38%        | +102.96%                 |        200 | £5,485            |
| t212_isa  | A_basket_rotation | 1D         |         93 | +0.28%        | -0.30%              | +0.91%              | -3.50%      | +8.60%                 |             0.11 |                   0.39 | +30.84%        | +127.52%                 |       2100 | £7,890            |
| t212_isa  | B_cheap_leg_only  | 1D         |         93 | -0.02%        | -0.34%              | +0.31%              | -2.63%      | +1.08%                 |            -0    |                   0.09 | -1.71%         | +127.52%                 |        808 | £4,687            |
| t212_isa  | C_inverse_etf_leg | 1D         |         93 | -0.08%        | -0.16%              | +0.01%              | -0.97%      | +0.00%                 |            -0.15 |                   0    | -6.81%         | +127.52%                 |        175 | £289              |

## Method notes

- Johansen trace/max-eigenvalue tests on log GBP prices, constant in the cointegrating relation, BIC lags.
- Benjamini-Hochberg FDR (q=0.05) across all groups tested in each formation window.
- Selection at each roll uses only data before the trading start; the hedge vector and z-score normalisation are fixed from the formation window.
- Long-only variants: A basket rotation, B cheap-leg only, C inverse-ETF leg. Benchmark is the equal-weight hold of all selected members.
- Costs per fill: half-spread (Corwin-Schultz estimate with floors), slippage, FX, stamp duty, PTM levy, fixed dealing fees (HL), whole-share rounding and next-bar fills for the manual account.
- Monthly return CIs: stationary block bootstrap (5000 resamples, mean block 3 months).
- Deflated Sharpe probability corrects the monthly Sharpe for the number of account/variant trials.

# Attainability report

Run `03d9214078f2431a` (as of 2026-10-31), config hash `ea992e15379e`, manifest hash `c070f83e2417`.

**Target:** 5%-20% per month at 95% confidence, net of all costs.

## Verdict

Best configuration: **t212_isa / C_inverse_etf_leg / 1D** with a geometric mean monthly return of +0.00% (95% CI +0.00% to +0.00%) over 168 months.

**Target not met.** The lower 95% bound (+0.00%/month) is below 5%/month. The table below is the achievable return as measured.

## Results (net of costs)

| account   | variant           | interval   |   n_months | monthly_geo   | monthly_geo_ci_lo   | monthly_geo_ci_hi   | p05_month   | prob_month_ge_target   |   monthly_sharpe |   deflated_sharpe_prob | total_return   | benchmark_total_return   |   n_trades | total_costs_gbp   |
|:----------|:------------------|:-----------|-----------:|:--------------|:--------------------|:--------------------|:------------|:-----------------------|-----------------:|-----------------------:|:---------------|:-------------------------|-----------:|:------------------|
| hl_sipp   | A_basket_rotation | 1D         |        168 | -1.15%        | -1.62%              | -0.71%              | -5.44%      | +0.00%                 |            -0.55 |                   0    | -85.70%        | +138.93%                 |       2720 | £88,128           |
| hl_sipp   | B_cheap_leg_only  | 1D         |        168 | -0.63%        | -0.90%              | -0.39%              | -3.04%      | +0.00%                 |            -0.54 |                   0    | -65.54%        | +138.93%                 |       1178 | £71,861           |
| hl_sipp   | C_inverse_etf_leg | 1D         |        168 | +0.00%        | +0.00%              | +0.00%              | +0.00%      | +0.00%                 |                  |                        | +0.00%         | +138.93%                 |          0 | £0                |
| t212_isa  | A_basket_rotation | 1D         |        168 | -0.08%        | -0.24%              | +0.08%              | -1.90%      | +0.00%                 |            -0.06 |                   0.02 | -12.23%        | +162.13%                 |       2668 | £6,835            |
| t212_isa  | B_cheap_leg_only  | 1D         |        168 | -0.09%        | -0.21%              | +0.04%              | -1.58%      | +0.00%                 |            -0.09 |                   0    | -13.46%        | +162.13%                 |       1126 | £4,879            |
| t212_isa  | C_inverse_etf_leg | 1D         |        168 | +0.00%        | +0.00%              | +0.00%              | +0.00%      | +0.00%                 |                  |                        | +0.00%         | +162.13%                 |          0 | £0                |

## Method notes

- Johansen trace/max-eigenvalue tests on log GBP prices, constant in the cointegrating relation, BIC lags.
- Benjamini-Hochberg FDR (q=0.05) across all groups tested in each formation window.
- Selection at each roll uses only data before the trading start; the hedge vector and z-score normalisation are fixed from the formation window.
- Long-only variants: A basket rotation, B cheap-leg only, C inverse-ETF leg. Benchmark is the equal-weight hold of all selected members.
- Costs per fill: half-spread (Corwin-Schultz estimate with floors), slippage, FX, stamp duty, PTM levy, fixed dealing fees (HL), whole-share rounding and next-bar fills for the manual account.
- Monthly return CIs: stationary block bootstrap (5000 resamples, mean block 3 months).
- Deflated Sharpe probability corrects the monthly Sharpe for the number of account/variant trials.

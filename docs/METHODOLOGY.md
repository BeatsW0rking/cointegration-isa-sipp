# Methodology

This document describes exactly what the pipeline computes so that every number in a report can be
traced to a decision here. Parameters live in `config/research.yaml`; this file explains them.

## 1. Universe and data

- **Seed universe**: LSE-listed UCITS ETFs from the official TradingView MCP screener (market `uk`,
  type `fund`, subtype `etf`, 30-day average volume >= 30k shares), excluding `0xxx` international
  lines and exotic quote currencies. Raw responses are committed under `data/seed_sources/`. The
  Trading 212 instrument list (`cointisa t212-cache`, needs API credentials) replaces this seed with
  the exact ISA-tradeable set when available.
- **Bars**: yfinance daily (full history), weekly, and hourly (about 730 days). Snapshots are
  parquet files under `data/snapshots/<as_of>/`, hashed in `data/manifest.json`.
- **Currency**: all prices are converted to GBP. Pence (GBX) are divided by 100; USD and EUR lines
  are divided by the GBPUSD / GBPEUR rate at the same bar (forward-filled, never look-ahead).
- **Liquidity**: median daily traded value over the last 60 daily bars >= £1m, and at least
  formation + validation bars of history.
- **Leverage**: leveraged and inverse products are excluded from candidate generation. Inverse
  ETFs are used only as the short leg in variant C.

## 2. Candidate groups

Testing every subset is infeasible. Log-return correlations are clustered (average linkage,
distance 1 - correlation, cut at correlation 0.6). Within a cluster every pair is a candidate; groups
of 3-5 are built from each member's six most correlated cluster-mates, scored by mean pairwise
correlation and capped at 500 per cluster. Ordering is deterministic.

## 3. Cointegration test

- **Pre-condition**: every member must be I(1) in the formation window. A series is I(0) only when
  ADF rejects a unit root *and* KPSS fails to reject stationarity; a lone 5% ADF rejection does not
  disqualify a random walk (it happens 5% of the time by construction).
- **Johansen** (statsmodels `coint_johansen`) on log GBP prices with a constant in the
  cointegrating relation (`det_order=0`) and the VAR lag chosen by BIC up to `max_lag`. Both the
  trace and maximum-eigenvalue statistics must indicate rank >= 1 at the 5% level. The first
  eigenvector, normalised to a leading 1, is the hedge vector `beta`.
- **Approximate p-value**: log-linear interpolation of the trace statistic between the 90/95/99%
  critical values. It is used only to rank candidates for FDR; the accept/reject decision uses the
  critical values directly.
- **False discovery control**: Benjamini-Hochberg with q = 0.05 across every group tested in the
  same formation window.
- **Spread quality**: Ornstein-Uhlenbeck half-life between 2 and 30 bars and Hurst exponent below
  0.5 on the formation spread.
- **Out-of-sample persistence** (research diagnostic, never used for selection): the formation
  `beta` is applied to the following validation window; the spread must have half-life within
  [2, 60] bars, ADF p < 0.10, and the re-estimated vector must lie within 20 degrees of the
  formation vector. Johansen significance is *not* required on the short validation window.

Why Johansen: it is the only standard test that handles more than two assets symmetrically and
estimates the rank. Engle-Granger is asymmetric in the choice of dependent variable and limited to
pairs; Phillips-Ouliaris shares that limitation. Partial cointegration (Clegg & Krauss 2018) and
Kalman-filter time-varying hedge ratios are noted as extensions, not used in v1.

## 4. Plausibility judge

A statistically cointegrated group is traded only if a judge assigns probability >= 0.5 to a durable
economic linkage. Backends share one interface and one committed cache:

- `rules`: deterministic taxonomy from names (same benchmark 0.95; FX share classes or hedged vs
  unhedged 0.90; inverse on same benchmark 0.85; heavy constituent overlap 0.6; linked commodities
  0.5; unclassified 0.15; unrelated 0.10).
- `claude`: Claude with a JSON schema output, low effort, prompt cached.
- `jev`: TypeSafe System One model; four atomic Noul questions combined in code.
- `clairic`: Cloudflare Workers AI extraction model (request schema to be verified).

Calibration: Brier score and reliability table against the persistence label, plus precision and
recall of the gate at several thresholds.

## 5. Signals and long-only variants

Spread `s_t = beta . log p_t`; `z_t = (s_t - mean_formation) / std_formation` with the formation
statistics held fixed through the trading period. A three-state signal with hysteresis: enter when
|z| >= 2.0, exit when |z| <= 0.5, stop when |z| >= 4.0, time stop after two half-lives tilted.
State +1 (spread rich) favours members with negative `beta`; state -1 favours positive `beta`.

- **A basket rotation**: equal-weight hold of the group; when tilted, the rich side's weight moves
  to the cheap side (weights proportional to |beta|).
- **B cheap-leg only**: hold only the cheap side when tilted, cash otherwise.
- **C inverse-ETF leg**: when tilted, half the slice in the cheap side and half in an inverse ETF on
  the rich side's benchmark (only where one exists; otherwise flat).

- **D long/short** (phase 2, shorting venues only): a genuine pairs trade. For spread
  `s = log A - b log B` in state -1 (spread cheap) hold long £x of A and short £b·x of B with
  `x(1+b)` equal to the group's slice times `gross_leverage`; state +1 mirrors it. Weights are the
  signed hedge-ratio weights normalised to unit gross. Benchmark is cash. Only pairs are traded
  (larger groups were shown to be spurious in phase 1).

Benchmark for variants A-C: equal-weight hold of all members ever selected, rebalanced on selection.

## 6. Selection without look-ahead

At each roll date a group is eligible if it passed FDR and quality at that formation end and at the
previous roll, and the judge gate passes. Trading starts the bar after the formation window closes.
The persistence label is never used for selection because it is computed on the trading window.

## 7. Execution and costs

Orders are generated at the bar close. The API account (Trading 212) fills at that close; the manual
account (HL) fills at the next bar close and rounds to whole shares. Each fill pays half the
estimated spread (Corwin-Schultz from high/low, floored at 5 bps for ETFs, 15 bps for inverse ETFs),
slippage (5 bps), FX (0.15% flat T212; marginal tiers at HL), stamp duty on UK share buys (not ETFs),
PTM levy over £10k, and fixed dealing fees (HL £6.95, or £3.95 after 20 trades the previous month).
Every figure in `config/costs.yaml` carries a source URL and the date checked.

### Shorting venues and financing (phase 2)

Three venues are modelled without opening an account: IG spread betting, Interactive Brokers margin
and Trading 212 CFD, plus two fee-free SIPPs (Trading 212, InvestEngine) for the long-only variants.
Per fill: the venue's spread markup is added to the estimated market spread; spread bets and CFDs
are exempt from stamp duty and the PTM levy; IBKR pays 0.05% commission (min £1) and stamp duty on
real UK share purchases; CFD FX applies to P&L only. Per bar, financing accrues on gross exposure:
longs pay (SONIA + markup), shorts receive (SONIA - markup) at IG (negative when the markup exceeds
the benchmark) or pay (SONIA + markup) at Trading 212 CFD, plus a borrow fee; at IBKR a 1x-gross
long is funded by cash and the short pays a general-collateral borrow fee with no interest on
proceeds below £80k. All rates are in `config/costs.yaml` with sources and dates and are marked for
verification against the live tariffs.

### Single-stock universe (phase 2)

FTSE 350 proxy: the 350 largest LSE ordinary shares by market cap from the TradingView screener
(investment trusts excluded), with sector and industry. Candidate clustering runs within sector so
every candidate shares an economic block; the rules judge scores same-industry pairs 0.6, same-sector
0.4, otherwise 0.1. Stocks are assumed UK-incorporated for stamp duty on real purchases (the seed
has no ISINs); the exempt venues are unaffected.

### Edge budget

For each qualifying pair, the capturable move per entry is (z_entry - z_exit) x formation spread
std in log terms per unit of gross exposure, realised only on the share of entries that exit on
reversion (measured from the zero-cost variant D run), compared with the round-trip cost per venue.
This is the quantity that bounds what any execution venue can deliver.

## 8. Attainability statistics

Monthly net returns from the equity curve. Stationary block bootstrap (mean block three months,
5000 resamples) gives 95% intervals for the mean and geometric mean monthly return, the 5th
percentile month, and the probability that a month returns at least 5%. The deflated Sharpe ratio
corrects the monthly Sharpe for the number of account x variant trials in the run. The report states
the target, the best lower bound, and whether the target is met.

## 9. Reproducibility

`uv.lock` pins dependencies; `config/*.yaml` carries every parameter; `data/manifest.json` hashes
every snapshot; the run id is the SHA-256 of configs and manifest. `results/<run_id>/run.json`
records the hashes; `tests/test_reproducible.py` runs the pipeline twice on fixture data and
compares the outputs byte for byte.

# Findings

Run `4f8e5cfd77309dca`, data as of 2026-10-31, LSE-listed UCITS ETFs, GBP terms, all costs included.
Full tables: `results/4f8e5cfd77309dca/attainability.md` and `attainability.csv`. Method:
[METHODOLOGY.md](METHODOLOGY.md).

## Headline

The 5-20% per month target is not attainable with long-only cointegration trading of LSE ETFs in a
Trading 212 ISA or an HL SIPP, on hourly, daily or weekly bars. The best of 108 account x variant x
timeframe x parameter configurations (daily bars) earns a geometric mean of **+0.66% per month** (95% bootstrap CI +0.05% to +1.32%) over 93
months, and that return is almost entirely market exposure: beta 0.81 against an equal-weight hold of
the same ETFs, annual alpha -0.8%, deflated Sharpe probability 0.37 (indistinguishable from the best
of 72 unskilled trials). Months returning 5% or more occurred 7.5% of the time.

## Daily bars (1D), 131 liquid ETFs, 10 years, 90 rolling windows

### Statistical screening

| | pairs | triples | quads | quints |
|---|---|---|---|---|
| group-windows tested | 20,712 | 32,809 | 37,839 | 27,120 |
| pass Johansen + FDR | 24% | 45% | 67% | 81% |
| ... and half-life/Hurst quality | 13% | 20% | 22% | 22% |
| persist 6 months out of sample | 1.4% | 1.1% | 0.7% | 0.5% |

- Cointegration "passes" rise with group size while out-of-sample persistence falls: the Johansen
  rank test finds a cointegrating vector in almost any five-asset group of index trackers. Large
  groups are overwhelmingly spurious and should not be traded.
- Only 4.4% of relationships that pass every in-sample filter still mean-revert with the formation
  hedge vector over the following six months.
- The relationships that do persist are the economically obvious ones: two S&P 500 trackers
  (IDUS/VUSD, 63% persistence across 16 windows), US Treasury ETF trios (CBU0/CBU7/IBTA), emerging
  market trackers (EMIM/SEMA, AUEM/XMME), gold and silver (IAUP/ISLN/SILG). The rules judge assigns
  these 0.90-0.95, which is the behaviour we wanted from the plausibility gate.

### Judge calibration (rules backend, 1,439 groups)

Brier 0.145. The judge separates same-benchmark groups from the rest, but even the 0.93-probability
bin persists only 1.4% of the time under the strict persistence label, because persistence of a fixed
hedge vector for six months is rare for every group. The gate's value is in excluding the unrelated
groups, not in predicting persistence.

### Backtests (net of costs, 93 months, 2018-2026)

Best configuration per account, pairs only, cost-aware entry (edge >= 1.5x round-trip cost):

| account | variant | monthly geo | 95% CI | CAGR | max DD | beta vs hold | alpha/yr | trades | costs |
|---|---|---|---|---|---|---|---|---|---|
| T212 ISA (£16k) | A basket rotation | +0.66% | +0.05% to +1.32% | 8.3% | -17% | 0.81 | -0.8% | 1,262 | £6,289 |
| T212 ISA | B cheap leg only | +0.17% | -0.12% to +0.48% | 2.2% | -12% | 0.23 | -0.4% | 454 | £3,375 |
| T212 ISA | C inverse ETF leg | -0.05% | -0.14% to +0.04% | -0.6% | -6% | -0.01 | -0.5% | 76 | £201 |
| HL SIPP (£85k) | A basket rotation | +0.30% | n/a | 3.7% | -23% | 0.83 | -4.4% | 967 | £61,983 |
| HL SIPP | B cheap leg only | +0.05% | n/a | 0.6% | -13% | 0.19 | -1.3% | 291 | £25,142 |
| HL SIPP | C inverse ETF leg | ~0 | n/a | -0.1% | -3% | 0.01 | -0.2% | 24 | £473 |

Buy-and-hold of the same equal-weight members returned +140% over the period (about +1.0%/month).

- **No variant has positive alpha** against simply holding the members. Variant A's positive return
  is the market beta it carries while rotating; variants B and C, which isolate the relative-value
  signal, are flat to negative after costs.
- **HL fees are prohibitive** at this trading frequency: £62k of dealing fees on £85k over eight years
  for variant A. Even with the cost-aware filter, fixed fees per deal destroy relative-value trading
  on whole-share lots at this scale.
- **Inverse ETFs (variant C)** cannot substitute for a short leg: daily-reset decay plus a 15 bps
  spread turn a near-zero-beta strategy into a slow bleed.
- **Group size**: pairs beat larger groups in every variant and account; the cost-aware filter helps
  modestly; raising the judge gate to 0.85 (same-benchmark only) reduces trades but does not create
  alpha.

## Weekly bars (1W), 133 liquid ETFs, 10 years, 97 rolling windows

Statistical screening shows the same size pattern (FDR pass rate 22% for pairs rising to 74% for
five-asset groups). The out-of-sample persistence diagnostic is uninformative at weekly resolution:
the 26-bar validation window gives the ADF test no power, so 0% of groups register as persistent.
This is a limitation of the diagnostic, not evidence that weekly relationships are worse.

Best configuration per account, pairs only, cost-aware entry:

| account | variant | monthly geo | 95% CI | CAGR | max DD | beta vs hold | alpha/yr | trades | costs |
|---|---|---|---|---|---|---|---|---|---|
| T212 ISA | A basket rotation | +0.56% | -0.01% to +1.11% | 7.0% | -17% | 0.57 | -0.4% | 572 | £7,998 |
| T212 ISA | B cheap leg only | +0.09% | n/a | 1.0% | -12% | 0.10 | -0.3% | 132 | £2,946 |
| T212 ISA | C inverse ETF leg | -0.02% | -0.06% to +0.02% | -0.2% | -3% | -0.01 | 0.0% | 16 | £77 |
| HL SIPP | A basket rotation | +0.21% | n/a | 2.4% | -17% | 0.56 | -3.9% | 542 | £62,527 |
| HL SIPP | B cheap leg only | +0.09% | -0.12% to +0.28% | 1.2% | -13% | 0.13 | -0.3% | 106 | £19,486 |
| HL SIPP | C inverse ETF leg | -0.03% | n/a | -0.3% | -4% | -0.02 | -0.1% | 3 | £176 |

Buy-and-hold of the same members returned +173% over the period. Fewer trades than daily (as
intended) but no alpha anywhere; the deflated Sharpe probability of the best weekly configuration is
0.33.

## Hourly bars (1h), 151 liquid ETFs, pairs only, 2.7 years, 47 rolling windows

Hourly data from Yahoo covers about 730 days, so the formation window (2,000 bars, about 11 months)
leaves 23 months of trading. Only pairs were screened at this resolution: the daily and weekly
results showed larger groups to be spurious, and the hourly sweep is the most expensive.

- Screening: 21% of pair-windows pass Johansen + FDR, 10% also pass quality, and **8.4% of those
  persist** out of sample, the highest persistence of the three timeframes, with a median half-life
  of 4.3 hours. The persistent pairs are again same-index or near-identical trackers: HMWO/V3AB,
  MIDD/VMID (FTSE 250), CBU0/CBU7 (US Treasuries), VHVG/VWRA, EIMI/IDEM.
- Trading them is the worst outcome of all: the spreads are tight, the entries are frequent, and
  the costs compound. With the cost-aware filter, Trading 212 variant A returns +0.19%/month
  (95% CI -2.0% to +2.3%) with beta 0.97 and alpha -13.7%/year against holding the pair; variant B
  loses 1.0%/month; variant C loses 0.6%/month. The HL SIPP loses 0.4-0.5%/month even after the
  filter, and 4-6%/month without it (£75-80k of fees on £85k in 23 months).

| account | variant | monthly geo | 95% CI | beta vs hold | alpha/yr | trades | costs |
|---|---|---|---|---|---|---|---|
| T212 ISA | A basket rotation | +0.19% | -2.01% to +2.27% | 0.97 | -13.7% | 2,275 | £7,075 |
| T212 ISA | B cheap leg only | -1.09% | -2.71% to +0.11% | 0.35 | -17.5% | 1,070 | £6,013 |
| T212 ISA | C inverse ETF leg | -0.56% | -1.33% to -0.01% | 0.11 | -7.8% | 887 | £2,881 |
| HL SIPP | A basket rotation | -0.49% | -2.92% to +1.57% | 0.90 | -17.7% | 1,131 | £41,808 |
| HL SIPP | B cheap leg only | -0.45% | -1.18% to +0.11% | 0.14 | -6.8% | 454 | £13,020 |
| HL SIPP | C inverse ETF leg | -0.02% | -0.07% to +0.03% | 0.00 | -0.1% | 63 | £992 |

Benchmark hold of the same pairs: +35% (HL) to +43% (T212) over the 23 months.

The 4h timeframe was not run separately: it would be a resample of the same hourly data with a
quarter of the bars, and it sits between two timeframes that already agree.

## Phase 2: following the three directions

### A genuine short leg (IG spread betting, IBKR margin, Trading 212 CFD; modelled, no account opened)

Variant D (dollar-neutral, hedge-ratio weighted pairs trade, pairs only, cost-aware entry) on the
same ETF screens, £20k capital, 93 months daily and weekly, 23 months hourly:

| venue | 1D monthly geo (95% CI) | 1D total | costs / financing | 1W total | 1h total |
|---|---|---|---|---|---|
| IBKR margin | -0.30% (-0.49% to -0.12%) | -24.4% | £4,042 / £162 | -21.2% | -25.6% |
| IG spread bet | -0.35% (-0.54% to -0.17%) | -27.6% | £4,672 / £1,033 | -23.0% | -26.9% |
| T212 CFD | -0.44% (-0.61% to -0.27%) | -33.6% | £6,072 / £2,502 | -33.7% | -31.9% |

- Capital does not matter (identical returns at £10k, £20k, £50k: the venues have no fixed fees in
  the model); **2x gross leverage doubles the loss** (-48%). Removing the cost-aware entry filter
  makes every venue worse.
- **The signal has no gross edge.** With every cost and financing charge set to zero, variant D
  returns -3.5% over 7.75 years (Sharpe -0.11) at the default thresholds and is negative at every
  threshold tried (|z| entry 1.5-2.5, pairs or groups to five). Of 624 entries, 72 (12%) exited on
  reversion, 193 (31%) hit the 4-sigma stop and 313 (50%) hit the two-half-life time stop. Costs
  then explain the rest of the loss: roughly 21 points of the 24% at IBKR.
- Edge budget (`results/<run_id>/edge_budget_1D_lse_etf.md`): median formation spread std 1.4%,
  so a 2-to-0.5 sigma round trip captures 2.1% of gross when it reverts; at the realised 12%
  reversion rate the expected edge per entry is 0.25%, below the 0.30% round trip at every venue.
  Only a minority of pairs (about 45%) show positive expected net edge even before financing, and
  those are not the ones that persist out of sample.

Conclusion: a short leg does not rescue the strategy on LSE ETFs. The venue only determines how fast
the costs are paid; the underlying mean-reversion signal does not deliver out of sample.

### A fee-free SIPP (Trading 212 SIPP, InvestEngine SIPP; long-only variants, pairs only)

| account | variant | 1D monthly geo (95% CI) | 1D total | benchmark hold | beta | alpha/yr | trades | costs |
|---|---|---|---|---|---|---|---|---|
| InvestEngine SIPP | A basket rotation | +0.78% (+0.19% to +1.42%) | +109% | +143% | 0.83 | +0.3% | 1,367 | £26,649 |
| InvestEngine SIPP | B cheap leg only | +0.25% (-0.02% to +0.52%) | +28% | +143% | 0.25 | +0.3% | 504 | £14,494 |
| T212 SIPP | A basket rotation | +0.66% (+0.06% to +1.32%) | +88% | +141% | 0.83 | -1.0% | 1,292 | £34,928 |
| T212 SIPP | B cheap leg only | +0.15% (-0.13% to +0.42%) | +16% | +141% | 0.23 | -0.7% | 458 | £18,818 |

Removing HL's fixed fee turns the SIPP from a certain loss into a market-tracking portfolio with
alpha within ±1% a year of zero: the same conclusion as the ISA. Costs are still large in cash
terms (£15-35k over eight years on £85k) because the spread is paid on every rotation; the cheaper
way to hold the same exposure is to buy and hold the members.

## Why the target is out of reach (mechanics, not luck)

1. A cointegrated pair of index trackers has a spread standard deviation of roughly 0.3-1.0% of
   price. Capturing one standard deviation per trade, net of 20-50 bps round-trip costs, leaves well
   under 0.5% per trade on the traded leg, with a half-life of 2-10 days and perhaps 2-6 trades a
   month per pair. That bounds the gross long-short edge at roughly 1-3% per month *with* a short
   leg and *without* capital constraints.
2. Long-only removes the short leg, so each trade carries full market risk and only half of the
   signal is usable; the relative-value profit is diluted into index beta.
3. The very relationships that persist (same-index trackers) have the smallest spreads, so they are
   the least profitable after costs; the groups with wide spreads do not persist.
4. The 5-20% per month target implies 80-800% per year. Nothing in the data, in any timeframe, variant
   or account, approaches an order of magnitude of that.

## What would change the answer

- A margin or CFD account allowing a genuine short leg (outside ISA/SIPP wrappers).
- Zero-fee, fractional execution for the SIPP (HL's tariff rules the SIPP out for this strategy;
  the SIPP would be better used for the buy-and-hold leg).
- Intraday data with real bid/ask to trade the tighter same-index spreads where the edge actually
  lives, at a venue where the round trip is under 5 bps.

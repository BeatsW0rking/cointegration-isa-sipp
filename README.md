# cointegration-isa-sipp

Reproducible research pipeline that finds cointegrated groups of instruments tradeable in a
Trading 212 Stocks & Shares ISA and a Hargreaves Lansdown SIPP, generates long-only
entry/exit signals from the cointegrating spread, and reports the **net** return achievable
after spread, FX, stamp duty and dealing fees, with bootstrap confidence intervals.

The research question is whether 5-20%/month at 95% confidence is attainable. The pipeline is
built to answer that honestly: the headline deliverable is `results/<run_id>/attainability.md`,
which reports the achieved figure whether or not it meets the target.

See [docs/PLAN.md](docs/PLAN.md) for the full design and [docs/METHODOLOGY.md](docs/METHODOLOGY.md)
for the statistical method.

## Quick start

```bash
uv sync --all-extras          # pinned environment from uv.lock
uv run pytest                 # unit, golden and reproducibility tests
uv run cointisa --help
```

## Pipeline

```
cointisa fetch-yf      -> snapshot 1W/1D/1h bars for config/universe_seed.csv via yfinance (+ FX)
cointisa ingest-plan   -> list of TradingView MCP calls to fill gaps (4h, symbols Yahoo lacks)
cointisa verify-data   -> check data/snapshots against data/manifest.json hashes
cointisa t212-cache    -> download the Trading 212 instrument list (needs T212_API_KEY/SECRET)
cointisa universe      -> build tradeable universe (T212 metadata + HL overlay + tiers)
cointisa costs         -> round-trip cost table per account for representative instruments
cointisa screen        -> candidates + parallel Johansen sweep, FDR, quality, OOS persistence
cointisa judge         -> economic-plausibility scores (rules / claude / jev / clairic) + calibration
cointisa backtest      -> walk-forward, cost-aware, long-only variants A/B/C, per account
cointisa report        -> bootstrap CIs, deflated Sharpe, attainability.md
cointisa signals       -> today's eligible groups, z-scores and target weights
cointisa paper-trade   -> Trading 212 orders (demo + dry-run by default; --live needs T212_ENV=live)
```

Typical research run for one timeframe:

```bash
uv run cointisa fetch-yf                 # once per as_of date (~1h for 737 symbols)
uv run cointisa screen --interval 1D     # ~40 min on 4 cores for ~240 liquid ETFs
uv run cointisa judge  --interval 1D
uv run cointisa backtest --interval 1D
uv run cointisa report --interval 1D     # prints results/<run_id>/attainability.md
```

## Status

Results are in [docs/FINDINGS.md](docs/FINDINGS.md) with full tables under `results/<run_id>/`.
Short version, two phases:

- **Phase 1 (long-only, ISA and HL SIPP):** statistical cointegration among LSE ETFs is abundant and
  mostly spurious; the relationships that persist are same-index trackers with tiny spreads; no
  long-only variant has positive alpha against holding the same ETFs once costs are included. HL's
  fixed fee rules the SIPP out for active trading.
- **Phase 2 (following the findings):** a genuine short leg (IG spread betting, IBKR margin,
  Trading 212 CFD; modelled, no account opened) loses 17-34% over the period at every venue and
  timeframe because the mean-reversion signal has no gross edge out of sample (12% of entries
  revert, the rest stop or time out); fee-free SIPPs (Trading 212, InvestEngine) turn the SIPP into
  a market tracker with zero alpha; FTSE 350 stocks are rarely cointegrated (3% of pair-windows) and
  lose on every venue. The 5-20%/month target is not attainable with this strategy class.

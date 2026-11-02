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

See [docs/METHODOLOGY.md](docs/METHODOLOGY.md) for the method and `results/<run_id>/attainability.md`
for the latest measured outcome. Honest summary of the pilot (40 ETFs, daily bars, 14 years):
statistical cointegration among LSE ETFs is common (about half of all group-windows pass FDR) but
only about 7% of those relationships persist six months out of sample with the formation hedge
vector, and the long-only variants returned roughly -0.1%/month net at Trading 212 and worse at HL,
where the fixed dealing fee dominates. The full-universe runs will replace these numbers.

## Reproducibility rules

- Dependencies pinned in `uv.lock`; every run config carries `as_of`, windows, thresholds and `seed`.
- Raw data is never modified in place. Snapshots live under `data/snapshots/<as_of>/` (gitignored);
  their SHA-256 hashes are committed in `data/manifest.json` and checked by `cointisa verify-data`.
- Run id = SHA-256 of (config + manifest). `results/<run_id>/summary.json` is committed; a rerun must
  reproduce it byte for byte (`tests/test_reproducible.py`).
- Secrets only via environment variables (see `.env.example`); nothing secret is ever committed.

## Accounts and constraints

| Account | Capital | Short selling | Fractional | API | Dealing fee | FX |
|---|---|---|---|---|---|---|
| Trading 212 ISA | ~£16k | No | Yes | Yes (market orders) | £0 | 0.15% each way |
| HL SIPP | ~£85k | No | No | No (manual) | £6.95 (£3.95 if 20+ trades prior month) | ~0.99% tiered |

All cost parameters live in `config/costs.yaml` with a source URL and date per figure.

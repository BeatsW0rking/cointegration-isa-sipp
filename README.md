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
cointisa ingest-plan   -> list of TradingView MCP calls to make for the configured universe
cointisa verify-data   -> check data/snapshots against data/manifest.json hashes
cointisa universe      -> build tradeable universe (T212 metadata + HL overlay + liquidity floor)
cointisa screen        -> Johansen sweep over candidate groups, FDR + persistence filters
cointisa judge         -> economic-plausibility scores (rules / claude / jev / clairic)
cointisa backtest      -> walk-forward, cost-aware, long-only variants A/B/C, per account
cointisa report        -> bootstrap CIs and attainability report
cointisa paper-trade   -> Trading 212 demo execution (later phase)
cointisa hl-report     -> manual trade list for the HL SIPP (later phase)
```

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

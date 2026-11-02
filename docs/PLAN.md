# Cointegration research for ISA (Trading 212) and SIPP (Hargreaves Lansdown)

## Context

Matt wants a reproducible research pipeline that finds cointegrated groups of instruments tradeable in a
Trading 212 Stocks & Shares ISA (~£16k) and a Hargreaves Lansdown SIPP (~£85k), generates entry/exit
signals from the cointegrating spread, and reports the net return achievable after spread, FX, stamp duty
and dealing fees. Target is 5-20%/month at 95% confidence; the pipeline must report the achievable figure
honestly even when it is far below that. End state: an automated Trading 212 ISA bot plus a signal report
for manual SIPP trades at HL.

Two constraints shape the whole design:

1. **ISA and SIPP cannot short.** Classic long/short pairs trading is impossible. Three long-only variants
   will be built and compared on identical data: (A) basket rotation, (B) long-the-cheap-leg only,
   (C) inverse ETF as the short leg where one exists.
2. **The return target is far above what the literature reports** for long/short pairs trading
   (roughly 1%/month gross, pre-cost, with leverage). The primary deliverable is therefore an unbiased
   estimate with confidence intervals, built so that negative results are as reproducible as positive ones.

"Type 1 model" means System One models (TypeSafe's Jev, Cloudflare's Clairic): non-generative models that
return typed answers with calibrated probabilities. They will be one backend of a pluggable
"economic plausibility judge" that gates statistically cointegrated groups.

## Facts established during planning (verified 2026-11-02)

- **Trading 212 API** (`/api/v0`): instruments + exchanges metadata, portfolio, cash, orders (live: market
  orders only via API), history/exports. **No candles or quotes.** Demo and live base URLs. Invest and ISA
  accounts supported. Rate limited per endpoint. Docs at docs.trading212.com.
- **TradingView official MCP**: connected and tested in this session. `get_ohlcv` serves 1m-1W bars
  (1h, 4h, 1D, 1W all confirmed on LSE:VUSA), 5000 bars/call, pages back via `next_date_to`, daily back to
  listing, intraday "a few thousand bars". `get_symbol_data_batch` gives 50 symbols/call with currency
  (mix of GBX, GBP, USD confirmed) and 30-day average volume; **bid/ask return null** (delayed feed), so
  spreads must be estimated. Screener (`market=uk`, `symbol_types=[fund]`) needs at least one filter.
  Inverse ETFs LSE:XSPS (S&P 500 inverse) and LSE:XUKS (FTSE 100 short) exist; ISA eligibility to be
  confirmed from the T212 instrument list. Tools are callable only from inside a Claude session, not
  from Python.
- **yfinance**: free; LSE tickers use `.L`; daily history unlimited; 1h bars ~730 days; no 4h (resample).
  LSE prices are often in pence (GBp); currency per instrument must come from T212 metadata.
- **Jev** (TypeSafe): typed questions -> probabilities, waitlist access, $0.042/M input tokens.
  **Clairic** (Cloudflare Workers AI `@cf/cloudflare/clairic`): extraction/estimation model, typed values
  with confidence, preview, $0.10/M input tokens, 64k context.
- **Costs** (third-party sources; to be confirmed against official tariffs in `config/costs.yaml`):
  T212 ISA: 0 commission, 0.15% FX each way, 0.5% stamp duty on UK share buys (ETFs/AIM exempt),
  PTM £1.50 on UK trades >£10k, fractional shares allowed.
  HL SIPP: £6.95/online share trade (£3.95 if 20+ trades prior month), FX ~0.99% tiered, 0.35% platform
  fee capped £150/yr for shares, no fractional, no API.
- **This cloud session** currently blocks every market-data host (Yahoo, T212, Stooq, EODHD, Cloudflare,
  typesafe.ai) and its GitHub token is invalid. Only PyPI and api.github.com are open.

## Prerequisites (Matt, before implementation session)

1. Repo exists: **https://github.com/BeatsW0rking/cointegration-isa-sipp**. First implementation step is
   `add_repo` with push access and clone into `/home/user/cointegration-isa-sipp`. If the attach is refused,
   reconnect GitHub at https://claude.ai/connect-github and install the Claude GitHub App on the repo.
2. In the environment settings, **Allowed domains** (keep package managers ticked):
   `query1.finance.yahoo.com`, `query2.finance.yahoo.com`, `docs.trading212.com`,
   `demo.trading212.com`, `live.trading212.com`, `api.anthropic.com`, `api.cloudflare.com`,
   `docs.typesafe.ai`, `api.typesafe.ai` (exact Jev host to confirm from their docs once allowed).
3. **Network secrets / env vars** (never pasted in chat): `T212_API_KEY`, `T212_API_SECRET`,
   `T212_ENV=demo` (demo first), `ANTHROPIC_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`,
   `TYPESAFE_API_KEY` (when the waitlist clears).
4. TradingView MCP connector: **done** (tested).
5. Copy this plan into the repo as `docs/PLAN.md` in the first commit so it survives the session.

## Repository layout

```
cointegration-isa-sipp/
  pyproject.toml, uv.lock            # Python 3.13, pinned deps (statsmodels, pandas, numpy, scipy,
                                     #   arch, yfinance, httpx, pydantic, typer, pyarrow, matplotlib)
  README.md, docs/PLAN.md, docs/METHODOLOGY.md, docs/COSTS.md
  config/
    universe.yaml                    # exchanges, asset types, liquidity floor, HL eligibility CSV path
    costs.yaml                       # per-account cost parameters with source URL + date per figure
    research.yaml                    # as_of date, timeframes, windows, thresholds, seeds
  src/cointisa/
    data/        providers (yfinance, tradingview_snapshot, t212_meta), fx, cache, manifest
    universe/    build universe from T212 instruments endpoint; HL eligibility overlay; currency map
    costs/       CostModel: spread, FX, stamp duty, PTM, fixed fees, fractional rules, per account
    stats/       stationarity (ADF/KPSS), johansen, engle_granger, ou_halflife, hurst, fdr
    screen/      candidate group generation + Johansen sweep + persistence filter
    judge/       PlausibilityJudge interface; rules, claude, jev, clairic backends; calibration
    signals/     VECM spread z-score; long-only variants A/B/C; position sizing
    backtest/    walk-forward event engine, cost-aware fills, alpha/beta decomposition
    report/      stationary block bootstrap CI, deflated Sharpe, attainability report (md + html)
    exec/        t212 client (demo/live), order ledger, kill switch; hl_signal_report
    cli.py       `cointisa fetch|universe|screen|judge|backtest|report|paper-trade|hl-report`
  data/          raw/ and snapshots/ gitignored; data/manifest.json committed (sha256 per file)
  results/       keyed by sha256(config + manifest) ; summary.json committed, large files gitignored
  tests/         unit + golden + reproducibility
  .github/workflows/ci.yml           # ruff, pytest, pipeline on fixture data
```

## Methodology

### Universe (`universe/`)
- Pull full instrument list from T212 metadata endpoint with the ISA key (what the ISA key returns is the
  ISA-tradeable set). Record ticker, ISIN, currency, exchange, type, min quantity, working schedule.
- Map to Yahoo symbols (LSE -> `.L`; US as-is). Store mapping with manual overrides file.
- HL SIPP eligibility: HL has no API; maintain `config/hl_eligible.csv` (ISIN list) that Matt exports or
  confirms; default assume LSE-listed ETFs and FTSE 350 shares are available at HL, US shares flagged.
- Liquidity floor: median daily traded value over 60 days >= £1m (configurable).
- Tiers run in order: (1) LSE-listed ETFs, (2) FTSE 350, (3) US stocks/ETFs incl. dual listings, (4) rest.

### Data (`data/`)
- Everything converted to **GBP** using GBPUSD/GBPEUR series; FX series also kept as a candidate
  variable in the Johansen system (hedged vs unhedged share classes cointegrate with FX).
- **Primary: TradingView MCP snapshots.** Claude pulls bars in-session (1W, 1D full history; 4h and 1h
  as deep as the feed allows, paging with `next_date_to`, `format=columns`) and writes
  `data/snapshots/<as_of>/tradingview/<symbol>_<interval>.parquet` plus a per-symbol metadata row
  (currency, type, avg volume) from `get_symbol_data_batch`. The ingestion is driven by a committed
  symbol list and a `cointisa ingest-plan` command that emits the exact tool calls to make, so the step is
  documented and checkable; reproducibility is via the hashed snapshot, not re-pull. Budget: ~100
  calls/min, so a 500-symbol tier at 4 intervals is ~1 hour of ingestion.
- **Secondary: yfinance** (automatable from Python/CI): 1d and 1w full history, 1h for 730 days.
  Used as an independent cross-check of the TradingView snapshot (price-level agreement test per
  symbol) and as the CI fixture source. Adjusted close for signals; raw close + dividends recorded for the
  backtest's cash flows.
- **Currency normalisation**: GBX (pence) -> GBP /100; USD lines -> GBP via GBPUSD bars at the same
  interval (`FX_IDC:GBPUSD` or `OANDA:GBPUSD`). Currency taken from TradingView metadata, cross-checked
  against T212 metadata.
- **Spread estimate**: bid/ask are null on the delayed feed, so use Corwin-Schultz from high/low at the
  trading interval, floored at the instrument's tick size; calibrate against a handful of live spreads
  Matt reads off the T212 app and records in `config/spread_calibration.csv`.
- Every provider writes parquet + sha256 to `data/manifest.json`; `cointisa verify-data` checks it.

### Cost model (`costs/`)
Per fill: half-spread + FX (0.15% T212 / tiered HL on non-GBP lines) + stamp duty 0.5% on UK share buys
+ PTM £1.50 if UK and >£10k + fixed fee (HL £6.95, or £3.95 when prior-month trades >= 20) + slippage
assumption for market orders (configurable, default 0.05%). HL positions rounded to whole shares and
assume next-session fill (manual execution). Every number in `costs.yaml` carries source and date.

### Cointegration (`stats/`, `screen/`)
- Johansen (statsmodels `coint_johansen`) trace and max-eigenvalue, constant in cointegrating relation,
  lag order by BIC on the levels VAR. Johansen is kept as the primary test; it is the right tool for
  >2 assets. Engle-Granger used only as a cheap pairwise pre-screen.
- Pre-condition: each series must test I(1) (ADF fail to reject + KPSS reject); I(0) series are dropped
  because they create spurious Johansen ranks.
- Candidate groups: not all subsets. Blocks by economic linkage (same benchmark, same issuer,
  dual listing, sector/country, commodity) then correlation clustering of log returns within block,
  then Johansen on groups of 2-5.
- **False-positive control**: Benjamini-Hochberg FDR across all tests in a run (q = 0.05), plus
  persistence: must be cointegrated in formation window and in the following validation window.
- Spread quality: OU half-life 2-30 bars at the chosen timeframe, Hurst < 0.5, hedge-vector stability
  across rolling windows (max angular drift threshold).
- Noted extensions (not in v1): partial cointegration (Clegg & Krauss), Kalman time-varying hedge ratio.

### Plausibility judge (`judge/`)
Interface: `score(group: list[InstrumentMeta], context: str) -> JudgeResult(prob, tags, backend, cached)`.
Backends:
- `rules`: deterministic taxonomy (same benchmark index 0.95, same issuer different currency line 0.98,
  dual listing/ADR 0.98, same sector+country 0.5, shared commodity 0.6, else 0.1).
- `claude`: structured JSON output, temperature 0, prompt and response cached by content hash
  (read the `claude-api` skill before writing this code).
- `jev`: typed question against instrument-metadata state, returns P(durable economic linkage).
  Dormant until `TYPESAFE_API_KEY` exists; client written against docs.typesafe.ai.
- `clairic`: Cloudflare Workers AI REST call returning a typed probability with confidence.
  Dormant until Cloudflare credentials exist.
Calibration: label = whether cointegration persisted in the out-of-sample window; report Brier score and
reliability diagram per backend; gate threshold tuned on formation data only.

### Signals and long-only variants (`signals/`)
Spread = Johansen eigenvector applied to log prices; z-score over rolling window; entry/exit thresholds
from config (defaults 2.0 / 0.5, stop at 4.0 or 2x half-life time stop).
- **A. Basket rotation**: hold the group, tilt weights toward undervalued member(s) proportional to z,
  bounded [0,1] per leg, summing to 1. Benchmark: equal-weight buy-and-hold of the same group.
- **B. Cheap-leg only**: long the undervalued member when z < -entry, flat otherwise. Benchmark: cash
  and the asset's own buy-and-hold.
- **C. Inverse ETF leg**: only for index-level groups where an ISA-eligible inverse ETF exists in the
  T212 list; use actual inverse ETF prices (captures daily-reset decay).
Each variant reports alpha and beta against its benchmark so market exposure is not mistaken for edge.

### Backtest and attainability (`backtest/`, `report/`)
- Walk-forward: 24-month formation, 6-month trading, rolled monthly; timeframes 1w, 1d, 4h, 1h.
- Per account (T212 £16k, HL £85k) with that account's cost model, position caps and whole-share rules.
- Monthly net returns -> stationary block bootstrap (Politis-Romano) -> 95% CI of mean monthly return,
  5th percentile month, and P(month >= 5%). Deflated Sharpe ratio to correct for number of trials.
- `results/<run_id>/attainability.md`: target vs achieved table, per variant, per timeframe, per account,
  gross vs net, with trial count. This is the headline deliverable regardless of outcome.

### Execution (`exec/`) — later phase, separate go-ahead for live
- T212 client: metadata, portfolio, cash, market orders (API supports only market orders live),
  idempotent client-side order ledger, max position and daily loss kill switch, `T212_ENV=demo` first.
- HL: `cointisa hl-report` writes a dated markdown/HTML list of trades to place manually, with whole-share
  quantities and the fee-adjusted expected edge; can be run as a scheduled task later.

## Reproducibility rules (enforced in CI)
- `uv.lock` pinned; `research.yaml` carries `as_of`, all windows, thresholds and `seed`.
- Raw data never modified in place; snapshot per `as_of`; manifest hashes committed.
- Run id = sha256(config + manifest); `results/<run_id>/summary.json` committed; rerun must reproduce
  identical summary (test `tests/test_reproducible.py` runs the pipeline twice on fixture data).
- Golden tests: Johansen output on a synthetic VECM with known rank; cost model on hand-computed fills.
- Notebooks executed via papermill from the CLI, never hand-run outputs committed.

## Implementation order
1. Scaffold, CI, data providers, universe builder, cost model, manifest (`cointisa fetch`, `universe`).
2. Stats engine, candidate generation, Johansen sweep, FDR + persistence (`cointisa screen`).
3. Judge interface, rules + Claude backends, Jev/Clairic stubs, calibration (`cointisa judge`).
4. Signals, variants A/B/C, walk-forward backtest, bootstrap CI, attainability report (`backtest`, `report`).
5. T212 demo execution module, HL signal report (`paper-trade`, `hl-report`).
6. Live ISA trading: only after step 4 results are reviewed and Matt explicitly approves.

## Verification
- `uv run pytest` green (unit, golden, reproducibility).
- `cointisa ingest-plan` lists the TradingView calls; after ingestion `cointisa verify-data` passes on
  a fresh clone, and the yfinance cross-check reports price agreement within 0.1% for every symbol.
- `cointisa screen` on the LSE ETF tier recovers known relationships (e.g. two S&P 500 trackers from
  different issuers, GBP-hedged vs unhedged lines with GBPUSD in the system) with FDR-adjusted p < 0.05.
- `cointisa backtest && cointisa report` produces `attainability.md` with CI table; running twice yields
  byte-identical `summary.json`.
- `cointisa paper-trade --dry-run` against T212 demo places and cancels one order end-to-end.

## Open items to confirm during implementation
- Exact HL FX tiers and current dealing fee from HL's tariff page; T212 fee page.
- Which inverse ETFs appear in the T212 ISA instrument list (variant C universe).
- Jev API host and request schema once docs.typesafe.ai is reachable.
- TradingView MCP tool list and history depth once the connector is attached.

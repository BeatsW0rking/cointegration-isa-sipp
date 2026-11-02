# Seed sources

Raw responses used to build `config/universe_seed.csv`, kept so the seed is reproducible.

- `tradingview_screener_2026-10-31/`: three `run_screener` calls on the official TradingView MCP,
  market `uk`, symbol type `fund`, filtered on `average_volume_30d_calc` in bands
  [30k, 80k], [80k, 250k], [250k, inf). Converted with `scripts/seed_from_screener.py`.

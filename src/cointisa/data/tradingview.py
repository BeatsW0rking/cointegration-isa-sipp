"""TradingView MCP snapshot tooling.

The MCP tools are only callable from inside a Claude session, not from Python. This module makes
that step reproducible: `ingest_plan` emits the exact calls to make, and `store_response` writes a
saved response (JSON) into the snapshot with a manifest entry.
"""

from __future__ import annotations

import json
from pathlib import Path

from cointisa.data.manifest import Manifest
from cointisa.data.store import bars_from_tv_columns, bars_from_tv_rows, snapshot_path, write_bars

TV_INTERVALS = {"1h": "1h", "4h": "4h", "1D": "1D", "1W": "1W"}


def ingest_plan(
    symbols: list[str], intervals: list[str], as_of: str, count: int = 5000
) -> list[dict]:
    """One entry per (symbol, interval). `date_to` is as_of so the snapshot is reproducible."""
    plan = []
    for sym in symbols:
        for iv in intervals:
            plan.append(
                {
                    "tool": "mcp-tv-get-ohlcv",
                    "args": {
                        "symbol": sym,
                        "interval": TV_INTERVALS[iv],
                        "count": count,
                        "format": "columns",
                        "date_to": as_of,
                    },
                    "save_as": f"data/raw/tradingview/{as_of}/{sym.replace(':', '_')}_{iv}.json",
                }
            )
    return plan


def store_response(
    json_path: Path, symbol: str, interval: str, as_of: str, manifest: Manifest
) -> Path:
    """Convert one or more saved get_ohlcv responses (pages) into a snapshot parquet."""
    with open(json_path) as fh:
        payload = json.load(fh)
    pages = payload if isinstance(payload, list) else [payload]
    frames = []
    for page in pages:
        if "bars" in page and isinstance(page["bars"], dict):
            frames.append(bars_from_tv_columns(page["bars"]))
        elif "bars" in page:
            frames.append(bars_from_tv_rows(page["bars"]))
        elif all(k in page for k in ("t", "o", "h", "l", "c", "v")):
            frames.append(bars_from_tv_columns(page))
        else:
            raise ValueError(f"unrecognised TradingView payload in {json_path}")
    import pandas as pd

    bars = pd.concat(frames, ignore_index=True)
    path = snapshot_path(as_of, "tradingview", symbol, interval)
    write_bars(bars, path)
    manifest.record(
        path,
        source="tradingview_mcp",
        symbol=symbol,
        provider_symbol=symbol,
        interval=interval,
        rows=int(len(bars)),
        first_t=int(bars["t"].min()),
        last_t=int(bars["t"].max()),
        raw_json=str(json_path),
    )
    return path

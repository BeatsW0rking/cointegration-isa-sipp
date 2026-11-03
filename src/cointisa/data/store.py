"""Bars storage.

Schema: t (int64 unix seconds UTC), o, h, l, c, v (float64), sorted and unique on t.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from cointisa.paths import SNAPSHOT_DIR

BAR_COLUMNS = ["t", "o", "h", "l", "c", "v"]
INTERVAL_SECONDS = {"1h": 3600, "4h": 14400, "1D": 86400, "1W": 7 * 86400}


def to_unix_seconds(idx: pd.DatetimeIndex) -> np.ndarray:
    """Resolution-independent conversion of a tz-aware DatetimeIndex to int64 unix seconds."""
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    delta = idx.tz_convert("UTC") - pd.Timestamp(0, tz="UTC")
    return (delta // pd.Timedelta(seconds=1)).to_numpy().astype("int64")


def normalise_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Enforce schema, drop duplicates and NaN closes, sort by time."""
    out = df[BAR_COLUMNS].copy()
    out["t"] = out["t"].astype("int64")
    for c in ("o", "h", "l", "c", "v"):
        out[c] = out[c].astype("float64")
    out = out.dropna(subset=["c"]).drop_duplicates(subset="t", keep="last")
    out = out.sort_values("t").reset_index(drop=True)
    return out


def snapshot_path(as_of: str, source: str, symbol: str, interval: str) -> Path:
    safe = symbol.replace(":", "_").replace("/", "_").replace("=", "_")
    return SNAPSHOT_DIR / as_of / source / f"{safe}_{interval}.parquet"


def write_bars(df: pd.DataFrame, path: Path) -> Path:
    """Write deterministic parquet (no row-group randomness, fixed metadata)."""
    bars = normalise_bars(df)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(bars, preserve_index=False)
    pq.write_table(table, path, compression="zstd", version="2.6", data_page_version="2.0")
    return path


def read_bars(path: Path) -> pd.DataFrame:
    return normalise_bars(pq.read_table(path).to_pandas())


def bars_to_series(bars: pd.DataFrame, field: str = "c") -> pd.Series:
    idx = pd.to_datetime(bars["t"], unit="s", utc=True)
    return pd.Series(bars[field].to_numpy(), index=idx, name=field)


def bars_from_tv_columns(payload: dict) -> pd.DataFrame:
    """Convert a TradingView MCP get_ohlcv response in format=columns to the bar schema."""
    bars = payload.get("bars", payload)
    return pd.DataFrame({k: np.asarray(bars[k]) for k in BAR_COLUMNS})


def bars_from_tv_rows(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)[BAR_COLUMNS]


def bars_from_yfinance(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance OHLCV frame (single ticker, auto_adjust=False) to the bar schema."""
    d = df.copy()
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    t = to_unix_seconds(pd.DatetimeIndex(d.index))
    return pd.DataFrame(
        {
            "t": t,
            "o": d["Open"].to_numpy(),
            "h": d["High"].to_numpy(),
            "l": d["Low"].to_numpy(),
            "c": d["Close"].to_numpy(),
            "v": d["Volume"].to_numpy(dtype="float64"),
        }
    )

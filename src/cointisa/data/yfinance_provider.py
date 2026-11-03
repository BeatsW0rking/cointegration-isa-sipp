"""Bulk bar download via yfinance. Automatable; used for bulk history and as a cross-check."""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import pandas as pd

from cointisa.data.manifest import Manifest
from cointisa.data.store import bars_from_yfinance, snapshot_path, to_unix_seconds, write_bars

log = logging.getLogger(__name__)

YF_INTERVAL = {"1h": "1h", "1D": "1d", "1W": "1wk"}
# yfinance intraday depth is ~730 days; daily/weekly unlimited
YF_PERIOD = {"1h": "730d", "1D": "max", "1W": "max"}


def fetch_bars(yf_symbol: str, interval: str, end: str | None = None) -> pd.DataFrame:
    import yfinance as yf

    if interval == "4h":
        raise ValueError("yfinance has no 4h interval; resample 1h with resample_bars")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = yf.download(
            yf_symbol,
            period=YF_PERIOD[interval],
            interval=YF_INTERVAL[interval],
            auto_adjust=False,
            actions=False,
            progress=False,
            threads=False,
        )
    if df is None or df.empty:
        return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])
    bars = bars_from_yfinance(df)
    if end is not None:
        cutoff = int(pd.Timestamp(end, tz="UTC").timestamp()) + 86400
        bars = bars[bars["t"] < cutoff]
    return bars


def fetch_meta(yf_symbol: str) -> dict:
    import yfinance as yf

    fi = yf.Ticker(yf_symbol).fast_info
    out = {}
    for k in ("currency", "exchange", "quoteType", "lastPrice", "marketCap"):
        try:
            out[k] = fi[k]
        except Exception:  # noqa: BLE001 - fast_info raises on missing keys
            out[k] = None
    return out


def snapshot_symbol(
    symbol: str, yf_symbol: str, interval: str, as_of: str, manifest: Manifest
) -> Path | None:
    bars = fetch_bars(yf_symbol, interval, end=as_of)
    if bars.empty:
        log.warning("no data for %s (%s)", symbol, yf_symbol)
        return None
    path = snapshot_path(as_of, "yfinance", symbol, interval)
    write_bars(bars, path)
    manifest.record(
        path,
        source="yfinance",
        symbol=symbol,
        provider_symbol=yf_symbol,
        interval=interval,
        rows=int(len(bars)),
        first_t=int(bars["t"].iloc[0]),
        last_t=int(bars["t"].iloc[-1]),
    )
    return path


def resample_bars(bars: pd.DataFrame, rule: str = "4h") -> pd.DataFrame:
    """Resample intraday bars (e.g. 1h -> 4h). Bins are anchored at midnight UTC."""
    idx = pd.to_datetime(bars["t"], unit="s", utc=True)
    df = bars.set_index(idx)
    agg = df.resample(rule, label="left", closed="left").agg(
        {"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"}
    )
    agg = agg.dropna(subset=["c"])
    agg["t"] = to_unix_seconds(pd.DatetimeIndex(agg.index))
    return agg.reset_index(drop=True)[["t", "o", "h", "l", "c", "v"]]

"""Load snapshots into aligned, base-currency price panels."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd

from cointisa.data.fx import to_base_currency
from cointisa.data.manifest import Manifest
from cointisa.data.store import bars_to_series, read_bars
from cointisa.instruments import Instrument
from cointisa.paths import CONFIG_DIR, DATA_DIR

TIER_SEEDS = {
    "lse_etf": CONFIG_DIR / "universe_seed.csv",
    "ftse350": CONFIG_DIR / "universe_seed_stocks.csv",
}


def seed_path_for_tier(tier: str) -> Path:
    return TIER_SEEDS.get(tier, CONFIG_DIR / "universe_seed.csv")


def load_seed_instruments(path: Path | None = None) -> dict[str, Instrument]:
    """Instrument objects from a seed CSV (ETFs: config/universe_seed.csv; stocks:
    config/universe_seed_stocks.csv). Interim until the T212 instrument list exists.

    Stocks are assumed UK-incorporated (country GB, stamp duty applies on real purchases); the
    seed has no ISINs, so Irish- or Jersey-incorporated LSE names are treated conservatively.
    ETFs are assumed Irish-domiciled (no stamp duty)."""
    path = path or CONFIG_DIR / "universe_seed.csv"
    out: dict[str, Instrument] = {}
    with open(path) as fh:
        for r in csv.DictReader(line for line in fh if not line.startswith("#")):
            lev = float(r.get("leverage") or 1.0)
            is_stock = r.get("type", "etf") == "stock"
            out[r["symbol"]] = Instrument(
                symbol=r["symbol"],
                name=r["name"],
                currency=r["currency"],
                exchange="LSE",
                type="inverse_etf" if lev < 0 else ("stock" if is_stock else "etf"),
                country="GB" if is_stock else "IE",
                tradingview=r.get("tradingview") or None,
                yfinance=r.get("yfinance") or None,
                hedged_to="GBP"
                if r.get("hedged", "False") == "True" and "GBP" in r["name"]
                else None,
                leverage=lev,
                sector=r.get("sector") or None,
                issuer=r.get("industry") or None,  # industry stored on the issuer slot for stocks
            )
    return out


def manifest_entries(as_of: str, interval: str, source: str = "yfinance") -> dict[str, dict]:
    man = Manifest()
    prefix = f"snapshots/{as_of}/{source}/"
    return {
        v["symbol"]: {**v, "path": DATA_DIR / k}
        for k, v in man.entries.items()
        if k.startswith(prefix) and v.get("interval") == interval
    }


def load_fx(as_of: str, interval: str, source: str = "yfinance") -> dict[str, pd.Series]:
    ent = manifest_entries(as_of, interval, source)
    fx = {}
    for key in ("GBPUSD", "GBPEUR"):
        if key in ent:
            fx[key] = bars_to_series(read_bars(ent[key]["path"]), "c")
    return fx


def align_weekly(s: pd.Series) -> pd.Series:
    """Providers stamp weekly bars on different weekdays per symbol; snap each to its Monday."""
    idx = pd.DatetimeIndex(s.index).tz_convert("UTC")
    monday = idx.normalize() - pd.to_timedelta(idx.dayofweek, unit="D")
    out = pd.Series(s.to_numpy(), index=monday, name=s.name)
    return out[~out.index.duplicated(keep="last")]


def load_close_panel(
    as_of: str,
    interval: str,
    instruments: dict[str, Instrument],
    source: str = "yfinance",
    base: str = "GBP",
    field: str = "c",
    min_rows: int = 250,
    max_ffill: int = 2,
) -> pd.DataFrame:
    """Wide frame of base-currency prices (columns = symbols), aligned on the union of bar times.

    Gaps of up to `max_ffill` bars are forward-filled (stale quote), longer gaps stay NaN.
    Non-positive prices are dropped. Columns with fewer than `min_rows` finite values are dropped.
    """
    ent = manifest_entries(as_of, interval, source)
    fx = load_fx(as_of, interval, source)
    if interval in {"1h", "4h"} and not fx:
        fx = load_fx(as_of, "1D", source)  # intraday FX falls back to daily rates
    cols: dict[str, pd.Series] = {}
    for sym, inst in instruments.items():
        if sym not in ent:
            continue
        bars = read_bars(ent[sym]["path"])
        s = bars_to_series(bars, field)
        s = s[s > 0]
        if interval == "1W":
            s = align_weekly(s)
        try:
            s = to_base_currency(s, inst, fx, base)
        except KeyError:
            continue
        if s.notna().sum() >= min_rows:
            cols[sym] = s
    if not cols:
        return pd.DataFrame()
    panel = pd.concat(cols, axis=1).sort_index()
    panel = panel.ffill(limit=max_ffill)
    return panel


def load_value_traded(
    as_of: str, instruments: dict[str, Instrument], lookback: int = 60
) -> pd.Series:
    """Median daily traded value in GBP over the last `lookback` daily bars, per symbol."""
    ent = manifest_entries(as_of, "1D")
    fx = load_fx(as_of, "1D")
    out = {}
    for sym, inst in instruments.items():
        if sym not in ent:
            continue
        bars = read_bars(ent[sym]["path"]).tail(lookback)
        try:
            close = to_base_currency(bars_to_series(bars, "c"), inst, fx)
        except KeyError:
            continue  # FX series not snapshotted (yet); symbol cannot be valued in GBP
        vol = bars_to_series(bars, "v")
        out[sym] = float(np.nanmedian(close.to_numpy() * vol.to_numpy()))
    return pd.Series(out, name="median_daily_value_gbp")


def history_rows(as_of: str, interval: str = "1D") -> pd.Series:
    ent = manifest_entries(as_of, interval)
    return pd.Series({s: int(v["rows"]) for s, v in ent.items()}, name="rows")

"""Universe construction from the Trading 212 instrument list plus overlays.

Steps: load raw T212 instruments -> map to TradingView / yfinance symbols -> classify (etf,
stock, inverse) -> apply HL eligibility overlay -> assign tier. Liquidity filtering happens
after bars exist.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pandas as pd

from cointisa.config import UniverseConfig
from cointisa.instruments import Instrument
from cointisa.paths import CONFIG_DIR, RAW_DIR

# T212 ticker suffix -> (exchange code for TradingView, yfinance suffix)
T212_SUFFIX = {
    "l_EQ": ("LSE", ".L"),
    "_US_EQ": ("US", ""),
    "d_EQ": ("XETR", ".DE"),
    "a_EQ": ("EURONEXT", ".AS"),
    "p_EQ": ("EURONEXT", ".PA"),
    "e_EQ": ("BME", ".MC"),
    "m_EQ": ("MIL", ".MI"),
    "s_EQ": ("SIX", ".SW"),
}

INVERSE_RE = re.compile(r"\b(inverse|short|bear|-1x|daily short)\b", re.I)
LEVERAGED_RE = re.compile(r"\b([23]x|leveraged|daily leveraged)\b", re.I)


def parse_t212_ticker(ticker: str) -> tuple[str, str, str] | None:
    """Return (root, exchange, yfinance_symbol) for a T212 ticker such as 'VUSAl_EQ'."""
    for suffix, (exch, yf_suffix) in T212_SUFFIX.items():
        if ticker.endswith(suffix):
            root = ticker[: -len(suffix)]
            root_yf = root.replace("_", "-")  # e.g. BRK_B -> BRK-B
            return root, exch, f"{root_yf}{yf_suffix}"
    return None


def load_overrides(path: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    if not path.exists():
        return out
    with open(path) as fh:
        rows = [r for r in csv.DictReader(line for line in fh if not line.startswith("#"))]
    for r in rows:
        out[r["t212_ticker"]] = r
    return out


def load_hl_eligible(path: Path) -> set[str] | None:
    """Return a set of ISINs, or None if the file has no rows (meaning: unknown, use defaults)."""
    if not path.exists():
        return None
    with open(path) as fh:
        rows = [r for r in csv.DictReader(line for line in fh if not line.startswith("#"))]
    return {r["isin"] for r in rows} or None


def classify(name: str, t212_type: str) -> tuple[str, float]:
    if t212_type == "ETF":
        if INVERSE_RE.search(name):
            return "inverse_etf", -1.0
        return "etf", 1.0
    if t212_type == "STOCK":
        return "stock", 1.0
    return "other", 1.0


def build_instruments(cfg: UniverseConfig, raw_dir: Path | None = None) -> list[Instrument]:
    raw_dir = raw_dir or RAW_DIR / "t212" / cfg.as_of
    with open(raw_dir / "instruments.json") as fh:
        raw = json.load(fh)
    overrides = load_overrides(CONFIG_DIR / Path(cfg.symbol_overrides_csv).name)
    hl = load_hl_eligible(CONFIG_DIR / Path(cfg.hl_eligibility_csv).name)
    out: list[Instrument] = []
    for r in raw:
        if r.get("type") not in {"ETF", "STOCK"}:
            continue
        parsed = parse_t212_ticker(r["ticker"])
        if parsed is None:
            continue
        root, exch, yf_sym = parsed
        itype, lev = classify(r.get("name", ""), r["type"])
        ov = overrides.get(r["ticker"], {})
        tv = ov.get("tradingview") or (f"{exch}:{root}" if exch != "US" else None)
        yf_sym = ov.get("yfinance") or yf_sym
        symbol = tv or f"US:{root}"
        isin = r.get("isin")
        country = isin[:2] if isin else None
        hl_ok: bool | None
        if hl is not None:
            hl_ok = isin in hl
        else:
            hl_ok = True if exch == "LSE" else None
        out.append(
            Instrument(
                symbol=symbol,
                name=r.get("name", root),
                isin=isin,
                currency=r.get("currencyCode", "GBP"),
                exchange=exch,
                type=itype,  # type: ignore[arg-type]
                country=country,
                t212_ticker=r["ticker"],
                tradingview=tv,
                yfinance=yf_sym,
                min_qty=None,
                hl_eligible=hl_ok,
                leverage=lev,
            )
        )
    return out


def assign_tier(inst: Instrument, cfg: UniverseConfig) -> str | None:
    for tier in cfg.tiers:
        exch_ok = (
            tier.exchange is None
            or (isinstance(tier.exchange, str) and inst.exchange == tier.exchange)
            or (isinstance(tier.exchange, list) and inst.exchange in tier.exchange)
            or (tier.exchange == "LSE" and inst.exchange == "LSE")
        )
        t = "etf" if inst.type in {"etf", "inverse_etf"} else inst.type
        if exch_ok and t in tier.types:
            return tier.id
    return None


def instruments_frame(insts: list[Instrument], cfg: UniverseConfig) -> pd.DataFrame:
    rows = []
    for i in insts:
        d = i.model_dump()
        d["tier"] = assign_tier(i, cfg)
        rows.append(d)
    return pd.DataFrame(rows)


def apply_liquidity_filter(
    frame: pd.DataFrame,
    median_daily_value_gbp: pd.Series,
    history_days: pd.Series,
    cfg: UniverseConfig,
) -> pd.DataFrame:
    f = frame.set_index("symbol")
    f["median_daily_value_gbp"] = median_daily_value_gbp
    f["history_days"] = history_days
    keep = (f["median_daily_value_gbp"] >= cfg.liquidity.min_median_daily_value_gbp) & (
        f["history_days"] >= cfg.liquidity.min_history_days
    )
    return f[keep].reset_index()

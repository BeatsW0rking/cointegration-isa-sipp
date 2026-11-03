"""Instrument metadata shared by every stage."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

InstrumentType = Literal["etf", "stock", "inverse_etf", "fx", "index", "other"]


class Instrument(BaseModel):
    """One tradeable line. `symbol` is the canonical key used in snapshots and results."""

    symbol: str  # canonical, e.g. "LSE:VUSA"
    name: str
    isin: str | None = None
    currency: str  # ISO 4217 as quoted; "GBX" means pence sterling
    exchange: str
    type: InstrumentType
    country: str | None = None  # incorporation country for stamp duty, e.g. "GB", "IE", "US"
    t212_ticker: str | None = None  # Trading 212 API ticker, e.g. "VUSAl_EQ"
    tradingview: str | None = None  # e.g. "LSE:VUSA"
    yfinance: str | None = None  # e.g. "VUSA.L"
    min_qty: float | None = None
    hl_eligible: bool | None = None  # None = unknown
    benchmark: str | None = None  # tracked index for ETFs, e.g. "S&P 500"
    issuer: str | None = None
    sector: str | None = None
    hedged_to: str | None = None  # currency an ETF share class is hedged to
    leverage: float = 1.0  # -1.0 for inverse daily ETFs

    @property
    def quote_scale_to_major(self) -> float:
        """Multiply quoted prices by this to express them in the major currency unit."""
        return 0.01 if self.currency.upper() in {"GBX", "GBP_PENCE"} else 1.0

    @property
    def major_currency(self) -> str:
        return "GBP" if self.currency.upper() in {"GBX", "GBP_PENCE"} else self.currency.upper()

    @property
    def uk_stamp_duty(self) -> bool:
        """SDRT applies to UK-incorporated shares, not ETFs/ETCs/AIM."""
        return self.type == "stock" and (self.country or "").upper() == "GB"

    @property
    def irish_stamp_duty(self) -> bool:
        return self.type == "stock" and (self.country or "").upper() == "IE"

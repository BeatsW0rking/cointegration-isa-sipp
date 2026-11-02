"""Typed configuration loaded from config/*.yaml. All research-affecting parameters live here."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from cointisa.paths import CONFIG_DIR


class FxTier(BaseModel):
    upto_gbp: float | None
    pct: float


class AccountCosts(BaseModel):
    label: str
    capital_gbp: float
    base_currency: str = "GBP"
    commission_fixed_gbp: float = 0.0
    commission_fixed_frequent_gbp: float | None = None
    frequent_trader_threshold: int | None = None
    commission_pct: float = 0.0
    fx_fee_pct: float | None = None
    fx_fee_tiers: list[FxTier] | None = None
    fractional_shares: bool
    min_order_gbp: float = 0.0
    api_execution: bool
    order_types_live: list[str] = Field(default_factory=lambda: ["market"])
    fill_delay_bars: int = 0
    slippage_pct: float = 0.0
    platform_fee_pct: float = 0.0
    platform_fee_cap_gbp: float = 0.0
    sources: list[dict[str, Any]] = Field(default_factory=list)


class Taxes(BaseModel):
    uk_stamp_duty_pct: float
    irish_stamp_duty_pct: float = 0.01
    ptm_levy_gbp: float
    ptm_levy_threshold_gbp: float
    us_sec_fee_pct_sell: float = 0.0
    sources: list[dict[str, Any]] = Field(default_factory=list)


class SpreadConfig(BaseModel):
    estimator: Literal["corwin_schultz", "fixed"] = "corwin_schultz"
    floor_bps: dict[str, float]
    calibration_csv: str


class CostsConfig(BaseModel):
    accounts: dict[str, AccountCosts]
    taxes: Taxes
    spread: SpreadConfig


class Liquidity(BaseModel):
    min_median_daily_value_gbp: float
    lookback_days: int
    min_history_days: int


class Tier(BaseModel):
    id: str
    description: str
    exchange: str | list[str] | None
    types: list[str]


class UniverseConfig(BaseModel):
    as_of: str
    base_currency: str
    liquidity: Liquidity
    tiers: list[Tier]
    hl_eligibility_csv: str
    symbol_overrides_csv: str
    fx_symbols: dict[str, dict[str, str]]


class ResearchConfig(BaseModel):
    as_of: str
    seed: int
    timeframes: list[str]
    formation_bars: dict[str, int]
    trade_bars: dict[str, int]
    roll_step_bars: dict[str, int]
    max_history_bars: dict[str, int] = Field(default_factory=dict)
    n_jobs: int = 0
    stationarity: dict[str, float]
    johansen: dict[str, Any]
    multiple_testing: dict[str, Any]
    spread_quality: dict[str, float]
    candidates: dict[str, Any]
    judge: dict[str, Any]
    signals: dict[str, float]
    variants: list[str]
    bootstrap: dict[str, Any]
    target: dict[str, float]


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def load_costs(path: Path | None = None) -> CostsConfig:
    return CostsConfig.model_validate(_load_yaml(path or CONFIG_DIR / "costs.yaml"))


def load_universe(path: Path | None = None) -> UniverseConfig:
    return UniverseConfig.model_validate(_load_yaml(path or CONFIG_DIR / "universe.yaml"))


def load_research(path: Path | None = None) -> ResearchConfig:
    return ResearchConfig.model_validate(_load_yaml(path or CONFIG_DIR / "research.yaml"))


def config_hash(*models: BaseModel) -> str:
    """Stable SHA-256 over the canonical JSON of one or more config models."""
    h = hashlib.sha256()
    for m in models:
        h.update(
            json.dumps(m.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        )
    return h.hexdigest()

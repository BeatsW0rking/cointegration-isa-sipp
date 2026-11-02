"""Trading 212 public API client (v0). Basic auth: API key as username, API secret as password.

Spec snapshot: docs/vendor/trading212-openapi-2026-11-02.yaml. Only Invest and Stocks ISA accounts.
Live environment supports market orders only via the API; sells use a negative quantity.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

from cointisa.paths import RAW_DIR

log = logging.getLogger(__name__)

BASE_URLS = {"demo": "https://demo.trading212.com", "live": "https://live.trading212.com"}

# Per-endpoint minimum spacing in seconds, from the published rate limits.
RATE_LIMITS = {
    "/api/v0/equity/metadata/instruments": 50.0,
    "/api/v0/equity/metadata/exchanges": 30.0,
    "/api/v0/equity/account/summary": 5.0,
    "/api/v0/equity/positions": 1.0,
    "/api/v0/equity/orders": 5.0,
}


class T212Error(RuntimeError):
    pass


class T212Client:
    def __init__(self, env: str | None = None, key: str | None = None, secret: str | None = None):
        self.env = env or os.environ.get("T212_ENV", "demo")
        if self.env not in BASE_URLS:
            raise ValueError("T212_ENV must be 'demo' or 'live'")
        key = key or os.environ.get("T212_API_KEY")
        secret = secret or os.environ.get("T212_API_SECRET")
        if not key or not secret:
            raise T212Error("T212_API_KEY and T212_API_SECRET must be set in the environment")
        self._client = httpx.Client(
            base_url=BASE_URLS[self.env],
            auth=(key, secret),
            timeout=30.0,
            headers={"Accept": "application/json"},
        )
        self._last_call: dict[str, float] = {}

    def _throttle(self, path: str) -> None:
        for prefix, spacing in RATE_LIMITS.items():
            if path.startswith(prefix):
                wait = self._last_call.get(prefix, 0.0) + spacing - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self._last_call[prefix] = time.monotonic()
                return

    def _request(self, method: str, path: str, **kw: Any) -> Any:
        self._throttle(path)
        for attempt in range(4):
            r = self._client.request(method, path, **kw)
            if r.status_code == 429:
                reset = float(r.headers.get("x-ratelimit-reset", 0)) - time.time()
                time.sleep(min(max(reset, 1.0), 60.0) * (attempt + 1))
                continue
            if r.status_code >= 400:
                raise T212Error(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
            return r.json() if r.content else None
        raise T212Error(f"{method} {path}: rate limited after retries")

    # ---- metadata ----------------------------------------------------------------------
    def instruments(self) -> list[dict]:
        return self._request("GET", "/api/v0/equity/metadata/instruments")

    def exchanges(self) -> list[dict]:
        return self._request("GET", "/api/v0/equity/metadata/exchanges")

    # ---- account -----------------------------------------------------------------------
    def account_summary(self) -> dict:
        return self._request("GET", "/api/v0/equity/account/summary")

    def positions(self) -> list[dict]:
        return self._request("GET", "/api/v0/equity/positions")

    def pending_orders(self) -> list[dict]:
        return self._request("GET", "/api/v0/equity/orders")

    # ---- orders ------------------------------------------------------------------------
    def place_market(self, ticker: str, quantity: float, extended_hours: bool = False) -> dict:
        body = {"ticker": ticker, "quantity": quantity, "extendedHours": extended_hours}
        return self._request("POST", "/api/v0/equity/orders/market", json=body)

    def place_limit(
        self, ticker: str, quantity: float, limit_price: float, tif: str = "DAY"
    ) -> dict:
        body = {
            "ticker": ticker,
            "quantity": quantity,
            "limitPrice": limit_price,
            "timeValidity": tif,
        }
        return self._request("POST", "/api/v0/equity/orders/limit", json=body)

    def cancel(self, order_id: int) -> None:
        self._request("DELETE", f"/api/v0/equity/orders/{order_id}")

    def order(self, order_id: int) -> dict:
        return self._request("GET", f"/api/v0/equity/orders/{order_id}")


def cache_instruments(client: T212Client, as_of: str) -> Path:
    """Save the instrument and exchange lists as raw JSON for the universe builder."""
    out_dir = RAW_DIR / "t212" / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    inst = client.instruments()
    with open(out_dir / "instruments.json", "w") as fh:
        json.dump(inst, fh, indent=0, sort_keys=True)
    exch = client.exchanges()
    with open(out_dir / "exchanges.json", "w") as fh:
        json.dump(exch, fh, indent=0, sort_keys=True)
    log.info("cached %d instruments, %d exchanges to %s", len(inst), len(exch), out_dir)
    return out_dir

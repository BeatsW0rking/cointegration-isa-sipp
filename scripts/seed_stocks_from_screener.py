"""Build config/universe_seed_stocks.csv from saved TradingView screener responses for UK stocks.

Usage: python -I scripts/seed_stocks_from_screener.py OUT.csv RESPONSE.json [RESPONSE.json ...]

Rows are LSE-listed ordinary shares with sector and industry from the screener. Investment trusts
are excluded (they are funds). The market-cap floor used in the screener approximates FTSE 350
membership; the exact index list is not available from the free screener.
"""

from __future__ import annotations

import csv
import json
import sys

EXCLUDE_INDUSTRY = {"Investment Trusts/Mutual Funds", "Investment Trusts or Mutual Funds"}


def main(out_path: str, inputs: list[str]) -> None:
    rows: dict[str, dict] = {}
    for path in inputs:
        with open(path) as fh:
            payload = json.load(fh)
        for r in payload["data"]["rows"]:
            sym = r.get("symbol", "")
            exch, _, root = sym.partition(":")
            if exch != "LSE" or not root or root[0] == "0":
                continue
            if (r.get("industry") or "") in EXCLUDE_INDUSTRY:
                continue
            if r.get("currency") not in {"GBX", "GBP", "USD", "EUR"}:
                continue
            rows[sym] = {
                "symbol": sym,
                "tradingview": sym,
                "yfinance": f"{root.replace('.', '-')}.L",
                "name": r.get("description") or root,
                "currency": r.get("currency"),
                "close": r.get("close"),
                "avg_volume_30d": r.get("average_volume_30d_calc"),
                "market_cap": r.get("market_cap_basic"),
                "sector": r.get("sector") or "",
                "industry": r.get("industry") or "",
                "leverage": 1.0,
                "hedged": False,
                "type": "stock",
            }
    out = sorted(rows.values(), key=lambda d: -(d["market_cap"] or 0))[:350]  # FTSE 350 proxy
    with open(out_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    sectors = {}
    for d in out:
        sectors[d["sector"]] = sectors.get(d["sector"], 0) + 1
    print(f"{len(out)} LSE stocks written to {out_path}")
    print("sectors:", dict(sorted(sectors.items(), key=lambda kv: -kv[1])))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])

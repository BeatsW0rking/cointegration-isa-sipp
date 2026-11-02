"""Build config/universe_seed.csv from saved TradingView screener responses (untrusted JSON input).

Usage: python -I scripts/seed_from_screener.py OUT.csv RESPONSE.json [RESPONSE.json ...]
"""

from __future__ import annotations

import csv
import json
import re
import sys

INVERSE_RE = re.compile(r"\b(inverse|short|bear)\b", re.I)
LEVERAGED_RE = re.compile(r"(\b[2-5]x\b|\bleveraged\b|-[2-5]x|\(-?[2-5]x\))", re.I)
HEDGED_RE = re.compile(r"\b(GBP|USD|EUR|CHF)[\s-]*hedged\b|\bhedged\b", re.I)


def main(out_path: str, inputs: list[str]) -> None:
    rows: dict[str, dict] = {}
    for path in inputs:
        with open(path) as fh:
            payload = json.load(fh)
        for r in payload["data"]["rows"]:
            sym = r.get("symbol", "")
            exch, _, root = sym.partition(":")
            if exch != "LSE" or not root:
                continue  # LSIN and other segments are not what the brokers route to
            desc = r.get("description") or ""
            subtype = r.get("subtype") or ""
            if subtype != "etf":
                continue  # closed-end funds (investment trusts) are stocks for our purposes
            if root[0] == "0" or (r.get("currency") not in {"GBP", "GBX", "USD", "EUR"}):
                continue  # 0xxx codes are LSE international lines; exotic currencies unusable here
            lev = -1.0 if INVERSE_RE.search(desc) else 1.0
            m = LEVERAGED_RE.search(desc)
            if m:
                digits = re.search(r"[2-5]", m.group(0))
                lev = (abs(lev) * float(digits.group(0))) * (1 if lev > 0 else -1) if digits else lev
            rows[sym] = {
                "symbol": sym,
                "tradingview": sym,
                "yfinance": f"{root}.L",
                "name": desc,
                "currency": r.get("currency"),
                "close": r.get("close"),
                "avg_volume_30d": r.get("average_volume_30d_calc"),
                "leverage": lev,
                "hedged": bool(HEDGED_RE.search(desc)),
                "type": "inverse_etf" if lev < 0 else "etf",
            }
    out = sorted(rows.values(), key=lambda d: d["symbol"])
    with open(out_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    n_lev = sum(1 for d in out if abs(d["leverage"]) != 1.0)
    n_inv = sum(1 for d in out if d["leverage"] < 0)
    print(f"{len(out)} LSE ETFs written to {out_path} ({n_inv} inverse, {n_lev} leveraged)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])

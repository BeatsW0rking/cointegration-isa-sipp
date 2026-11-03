"""Manual trade list for the Hargreaves Lansdown SIPP (no API): whole-share quantities, fee-adjusted
expected edge, and the reasoning, written as markdown for the day."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_hl_report(intents: pd.DataFrame, as_of: str, out_dir: Path, fixed_fee: float) -> Path:
    """`intents` columns: group, symbol, name, side, shares, price_gbp, notional_gbp, z, half_life,
    expected_edge_pct, reason."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"hl_trades_{as_of}.md"
    lines = [f"# HL SIPP trade list for {as_of}", ""]
    if intents.empty:
        lines.append("No trades today.")
    else:
        lines.append(
            "Place as online share deals at the next open. Quantities are whole shares; the fee "
            f"column assumes £{fixed_fee:.2f} per deal. Skip any line whose expected edge is below "
            "its cost."
        )
        lines.append("")
        t = intents.copy()
        t["fee_pct"] = fixed_fee / t["notional_gbp"]
        t["net_edge_pct"] = t["expected_edge_pct"] - t["fee_pct"]
        cols = [
            "group",
            "symbol",
            "name",
            "side",
            "shares",
            "price_gbp",
            "notional_gbp",
            "z",
            "half_life",
            "expected_edge_pct",
            "fee_pct",
            "net_edge_pct",
            "reason",
        ]
        for c in ["expected_edge_pct", "fee_pct", "net_edge_pct"]:
            t[c] = t[c].map(lambda v: f"{v:+.2%}")
        t["price_gbp"] = t["price_gbp"].map(lambda v: f"£{v:,.2f}")
        t["notional_gbp"] = t["notional_gbp"].map(lambda v: f"£{v:,.0f}")
        lines.append(t[cols].to_markdown(index=False))
    path.write_text("\n".join(lines) + "\n")
    return path

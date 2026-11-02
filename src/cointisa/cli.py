"""Command-line entry points. Each stage reads config/*.yaml and writes to data/ or results/."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cointisa.config import load_costs, load_research, load_universe
from cointisa.paths import CONFIG_DIR, DATA_DIR, RAW_DIR

app = typer.Typer(add_completion=False, help="Reproducible cointegration research for ISA/SIPP.")
console = Console()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@app.command()
def verify_data() -> None:
    """Check every snapshot in data/manifest.json against its recorded SHA-256."""
    from cointisa.data.manifest import Manifest

    ok, bad, missing = Manifest().verify()
    console.print(
        f"[green]{len(ok)} ok[/green], [red]{len(bad)} mismatched[/red], "
        f"[yellow]{len(missing)} missing[/yellow]"
    )
    for rel in bad:
        console.print(f"  mismatch: {rel}")
    for rel in missing:
        console.print(f"  missing:  {rel}")
    raise typer.Exit(code=1 if bad else 0)


@app.command()
def ingest_plan(
    symbols_csv: Path = typer.Option(
        CONFIG_DIR / "universe_seed.csv", help="CSV with a 'tradingview' column"
    ),
    intervals: str = typer.Option("1W,1D,4h,1h"),
    out: Path = typer.Option(DATA_DIR / "ingest_plan.json"),
) -> None:
    """Emit the TradingView MCP calls needed to snapshot the configured universe."""
    import pandas as pd

    from cointisa.data.tradingview import ingest_plan as _plan

    ucfg = load_universe()
    seed = pd.read_csv(symbols_csv, comment="#")
    syms = [s for s in seed["tradingview"].dropna().unique().tolist()]
    syms += [v["tradingview"] for v in ucfg.fx_symbols.values()]
    plan = _plan(syms, intervals.split(","), ucfg.as_of)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=1))
    console.print(f"{len(plan)} calls written to {out}")


@app.command()
def fetch_yf(
    symbols_csv: Path = typer.Option(CONFIG_DIR / "universe_seed.csv"),
    intervals: str = typer.Option("1W,1D,1h"),
    limit: int = typer.Option(0, help="Only the first N symbols (0 = all)"),
) -> None:
    """Snapshot bars for the seed universe via yfinance and record them in the manifest."""
    import pandas as pd

    from cointisa.data.manifest import Manifest
    from cointisa.data.yfinance_provider import snapshot_symbol

    ucfg = load_universe()
    seed = pd.read_csv(symbols_csv, comment="#")
    rows = seed.dropna(subset=["yfinance"]).to_dict("records")
    if limit:
        rows = rows[:limit]
    fx_rows = [{"symbol": k, "yfinance": v["yfinance"]} for k, v in ucfg.fx_symbols.items()]
    man = Manifest()
    n = 0
    for r in rows + fx_rows:
        for iv in intervals.split(","):
            p = snapshot_symbol(r["symbol"], r["yfinance"], iv, ucfg.as_of, man)
            n += p is not None
        man.save()
    console.print(f"{n} snapshots written for as_of={ucfg.as_of}")


@app.command()
def t212_cache() -> None:
    """Download the Trading 212 instrument and exchange lists (needs T212_API_KEY/SECRET)."""
    from cointisa.data.t212 import T212Client, cache_instruments

    ucfg = load_universe()
    out = cache_instruments(T212Client(), ucfg.as_of)
    console.print(f"cached to {out}")


@app.command()
def universe() -> None:
    """Build the instrument table from the cached T212 list and overlays."""
    from cointisa.universe.build import build_instruments, instruments_frame

    ucfg = load_universe()
    raw = RAW_DIR / "t212" / ucfg.as_of
    if not (raw / "instruments.json").exists():
        console.print(f"[red]no T212 cache at {raw}; run `cointisa t212-cache` first[/red]")
        raise typer.Exit(1)
    insts = build_instruments(ucfg)
    frame = instruments_frame(insts, ucfg)
    out = DATA_DIR / "universe" / f"{ucfg.as_of}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out, index=False)
    t = Table("tier", "count")
    for tier, n in frame["tier"].value_counts(dropna=False).items():
        t.add_row(str(tier), str(n))
    console.print(t)
    console.print(f"written {out}")


@app.command()
def costs(notional: float = 3000.0, spread_bps: float = 10.0) -> None:
    """Show round-trip cost per account for representative instrument types."""
    from cointisa.costs.model import CostModel
    from cointisa.instruments import Instrument

    cfg = load_costs()
    examples = [
        Instrument(
            symbol="LSE:VUSA",
            name="GBP ETF",
            currency="GBP",
            exchange="LSE",
            type="etf",
            country="IE",
        ),
        Instrument(
            symbol="LSE:CSPX",
            name="USD ETF (LSE)",
            currency="USD",
            exchange="LSE",
            type="etf",
            country="IE",
        ),
        Instrument(
            symbol="LSE:SHEL",
            name="UK share",
            currency="GBX",
            exchange="LSE",
            type="stock",
            country="GB",
        ),
        Instrument(
            symbol="NASDAQ:AAPL",
            name="US share",
            currency="USD",
            exchange="NASDAQ",
            type="stock",
            country="US",
        ),
    ]
    t = Table(
        "instrument",
        *cfg.accounts.keys(),
        title=f"Round-trip cost, £{notional:,.0f} clip, {spread_bps} bps spread",
    )
    for inst in examples:  # noqa: F402
        row = [inst.name]
        for acc in cfg.accounts:
            row.append(
                f"{CostModel(cfg, acc).round_trip_pct(inst, notional, spread_bps / 1e4) * 100:.2f}%"
            )
        t.add_row(*row)
    console.print(t)


@app.command()
def show_config() -> None:
    """Print the research config and its hash (part of the run id)."""
    from cointisa.config import config_hash

    r = load_research()
    console.print_json(json.dumps(r.model_dump(mode="json")))
    console.print(f"config hash: {config_hash(r, load_costs(), load_universe())}")


if __name__ == "__main__":
    app()

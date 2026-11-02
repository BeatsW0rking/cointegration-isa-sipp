"""Command-line entry points. Each stage reads config/*.yaml and writes to data/ or results/."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

import cointisa._threads  # noqa: F401  (must precede numpy imports)
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
    for r in fx_rows + rows:  # FX first so later symbols can be valued in GBP
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


@app.command()
def screen(
    interval: str = typer.Option("1D"),
    tier: str = typer.Option("lse_etf"),
    max_symbols: int = typer.Option(0, help="Debug: cap the number of symbols (0 = all)"),
    exclude_leveraged: bool = typer.Option(
        True, help="Drop leveraged/inverse products from candidates"
    ),
    max_size: int = typer.Option(0, help="Override johansen.max_group_size (0 = config)"),
) -> None:
    """Candidate generation + Johansen sweep for one timeframe -> results/<run_id>/screen_*."""
    from cointisa.data.panel import (
        load_close_panel,
        load_seed_instruments,
        load_value_traded,
        seed_path_for_tier,
    )
    from cointisa.runid import run_dir, stage_manifest
    from cointisa.screen.candidates import candidate_groups
    from cointisa.screen.sweep import SweepConfig, sweep

    rcfg, ucfg = load_research(), load_universe()
    insts = load_seed_instruments(seed_path_for_tier(tier))
    if exclude_leveraged:
        insts = {k: v for k, v in insts.items() if abs(v.leverage) == 1.0}
    # liquidity filter on daily bars
    mdv = load_value_traded(rcfg.as_of, insts, ucfg.liquidity.lookback_days)
    liquid = mdv[mdv >= ucfg.liquidity.min_median_daily_value_gbp].index
    insts = {k: v for k, v in insts.items() if k in set(liquid)}
    if max_symbols:
        insts = dict(list(insts.items())[:max_symbols])
    min_rows = rcfg.formation_bars[interval] + rcfg.trade_bars[interval]
    panel = load_close_panel(rcfg.as_of, interval, insts, min_rows=min_rows)
    cap = rcfg.max_history_bars.get(interval)
    if cap and len(panel) > cap:
        panel = panel.iloc[-cap:].dropna(axis=1, thresh=min_rows)
    console.print(
        f"panel {panel.shape[0]} bars x {panel.shape[1]} symbols ({interval}), {len(liquid)} liquid"
    )
    groups, clusters = candidate_groups(
        panel,
        threshold=rcfg.candidates["correlation_cluster_threshold"],
        min_size=rcfg.johansen["min_group_size"],
        max_size=max_size or rcfg.johansen["max_group_size"],
        cap_per_cluster=rcfg.candidates["max_groups_per_block"],
        min_overlap=min(200, rcfg.formation_bars[interval] // 2),
    )
    console.print(f"{len(clusters)} clusters, {len(groups)} candidate groups")
    scfg = SweepConfig(
        formation_bars=rcfg.formation_bars[interval],
        validation_bars=rcfg.trade_bars[interval],
        roll_step=rcfg.roll_step_bars[interval],
        det_order=rcfg.johansen["det_order"],
        max_lag=rcfg.johansen["max_lag"],
        alpha=rcfg.johansen["trace_alpha"],
        fdr_q=rcfg.multiple_testing["q"],
        half_life_min=rcfg.spread_quality["half_life_min_bars"],
        half_life_max=rcfg.spread_quality["half_life_max_bars"],
        hurst_max=rcfg.spread_quality["hurst_max"],
        max_angle_deg=rcfg.spread_quality["hedge_vector_max_angle_deg"],
        adf_alpha=rcfg.stationarity["adf_alpha"],
        kpss_alpha=rcfg.stationarity["kpss_alpha"],
    )
    res = sweep(panel, groups, scfg, n_jobs=rcfg.n_jobs)
    out = run_dir() / f"screen_{interval}_{tier}.parquet"
    res.to_parquet(out, index=False)
    sidecar = stage_manifest(list(panel.columns), rcfg.as_of, interval)
    sidecar.update(
        {"n_bars": int(len(panel)), "n_groups": len(groups), "max_size": max_size or None}
    )
    (run_dir() / f"screen_{interval}_{tier}.manifest.json").write_text(
        json.dumps(sidecar, indent=1)
    )
    clusters_out = run_dir() / f"clusters_{interval}_{tier}.json"
    clusters_out.write_text(json.dumps({str(k): v for k, v in clusters.items()}, indent=1))
    if res.empty:
        console.print("[yellow]no results[/yellow]")
        return
    summary = (
        res.groupby("form_end")[["pass_fdr", "persistent"]]
        .sum()
        .astype(int)
        .assign(tested=res.groupby("form_end").size())
    )
    console.print(summary.to_string())
    top = res[res["persistent"]].sort_values("p_fdr").head(15)
    console.print(
        top[
            ["group", "form_end", "p_fdr", "half_life", "hurst", "val_half_life", "val_angle_deg"]
        ].to_string()
    )
    console.print(f"written {out}")


@app.command()
def judge(
    interval: str = typer.Option("1D"),
    tier: str = typer.Option("lse_etf"),
    backends: str = typer.Option("", help="Comma list; default from research.yaml"),
    max_groups: int = typer.Option(0, help="Debug cap on distinct groups scored (0 = all)"),
) -> None:
    """Score every group that passed FDR in the screen with each judge backend; calibrate."""
    import pandas as pd

    from cointisa.data.panel import load_seed_instruments, seed_path_for_tier
    from cointisa.judge.calibrate import brier_score, gate_sweep, reliability_table
    from cointisa.judge.registry import make_judge
    from cointisa.runid import run_dir

    rcfg = load_research()
    names = [b for b in (backends.split(",") if backends else rcfg.judge["backends"]) if b]
    res = pd.read_parquet(run_dir() / f"screen_{interval}_{tier}.parquet")
    cand = res[res["pass_fdr"] & res["pass_quality"]]
    groups = sorted(cand["group"].unique().tolist())
    if max_groups:
        groups = groups[:max_groups]
    insts = load_seed_instruments(seed_path_for_tier(tier))
    label = cand.groupby("group")["persistent"].mean().rename("persist_rate")
    out_rows = []
    for name in names:
        j = make_judge(name)
        if not j.available:
            console.print(f"[yellow]{name}: credentials missing, skipped[/yellow]")
            continue
        for g in groups:
            members = [insts[s] for s in g.split("|") if s in insts]
            if len(members) != len(g.split("|")):
                continue
            r = j.score(members)
            out_rows.append(
                {
                    "group": g,
                    "backend": name,
                    "prob": r.prob,
                    "tags": ",".join(r.tags),
                    "rationale": r.rationale,
                    "cached": r.cached,
                }
            )
        console.print(f"{name}: scored {len(groups)} groups")
    if not out_rows:
        raise typer.Exit(1)
    df = pd.DataFrame(out_rows).merge(label, left_on="group", right_index=True, how="left")
    df["label"] = (df["persist_rate"] >= 0.5).astype(int)
    out = run_dir() / f"judge_{interval}_{tier}.parquet"
    df.to_parquet(out, index=False)
    for name, sub in df.groupby("backend"):
        console.print(
            f"\n[bold]{name}[/bold]  Brier={brier_score(sub['prob'], sub['label']):.3f}  "
            f"n={len(sub)}"
        )
        console.print(
            reliability_table(sub["prob"].to_numpy(), sub["label"].to_numpy()).to_string()
        )
        console.print(gate_sweep(sub["prob"].to_numpy(), sub["label"].to_numpy()).to_string())
    console.print(f"written {out}")


@app.command()
def backtest(
    interval: str = typer.Option("1D"),
    tier: str = typer.Option("lse_etf"),
    accounts: str = typer.Option("t212_isa,hl_sipp"),
    variants: str = typer.Option("", help="Comma list; default from research.yaml"),
    judge_backend: str = typer.Option("rules", help="Judge used for the plausibility gate"),
    max_groups: int = typer.Option(5),
    stability_windows: int = typer.Option(
        1, help="Group must also have passed in the N previous rolls"
    ),
    max_size: int = typer.Option(5, help="Ignore groups with more members than this"),
    min_edge_multiple: float = typer.Option(
        0.0, help="Enter only if expected edge >= k x round-trip cost"
    ),
    gate: float = typer.Option(-1.0, help="Judge gate probability (default from research.yaml)"),
    capital: float = typer.Option(0.0, help="Override account capital in GBP (0 = costs.yaml)"),
    gross_leverage: float = typer.Option(1.0, help="Variant D: gross exposure per group / slice"),
) -> None:
    """Walk-forward backtest of screened groups, per account and variant (long-only or L/S)."""
    import hashlib

    import pandas as pd

    from cointisa.backtest.engine import BacktestConfig, run_backtest
    from cointisa.backtest.prepare import build_selections, inverse_etf_map, spread_panel
    from cointisa.costs.model import CostModel
    from cointisa.data.panel import load_close_panel, load_seed_instruments, seed_path_for_tier
    from cointisa.judge.registry import make_judge
    from cointisa.runid import costs_hash, run_dir

    rcfg, ccfg = load_research(), load_costs()
    insts = load_seed_instruments(seed_path_for_tier(tier))
    screen_df = pd.read_parquet(run_dir() / f"screen_{interval}_{tier}.parquet")
    needed = sorted({s for g in screen_df["group"] for s in g.split("|")})
    inv_map = inverse_etf_map(insts)
    needed += [v for v in inv_map.values() if v in insts]
    sub = {k: insts[k] for k in dict.fromkeys(needed) if k in insts}
    panel = load_close_panel(rcfg.as_of, interval, sub, min_rows=50)
    spreads = spread_panel(rcfg.as_of, interval, sub, ccfg, panel)
    inv_map = {k: v for k, v in inv_map.items() if v in panel.columns}
    sub = {k: v for k, v in sub.items() if k in panel.columns}
    judge = make_judge(judge_backend)
    gate = float(rcfg.judge["gate_probability"]) if gate < 0 else gate
    selections = build_selections(
        screen_df, panel, insts, judge, gate, rcfg, interval, stability_windows
    )
    console.print(
        f"{sum(len(s.models) for s in selections)} group-selections across {len(selections)} roll dates"
    )
    start_bar = min((s.start for s in selections), default=len(panel))
    bars_per_year = {"1W": 52, "1D": 252, "4h": 252 * 2, "1h": 252 * 8}[interval]
    rows = []
    params = {
        "judge": judge_backend,
        "gate": gate,
        "max_groups": max_groups,
        "stability_windows": stability_windows,
        "max_size": max_size,
        "min_edge_multiple": min_edge_multiple,
        "capital": capital or None,
        "gross_leverage": gross_leverage,
        "costs_hash": costs_hash(),
        "accounts": accounts,
    }
    phash = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:8]
    out_dir = run_dir() / f"backtest_{interval}_{tier}_{phash}"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "params.json").write_text(json.dumps(params, indent=1))
    for acc in accounts.split(","):
        cm = CostModel(ccfg, acc)
        if capital:
            cm.acc = cm.acc.model_copy(update={"capital_gbp": capital})
        for var in variants.split(",") if variants else rcfg.variants:
            if var == "D_long_short" and not cm.acc.allow_short:
                console.print(f"[yellow]{acc}: long-only account, skipping {var}[/yellow]")
                continue
            if var != "D_long_short" and cm.acc.allow_short:
                console.print(f"[yellow]{acc}: shorting venue, skipping long-only {var}[/yellow]")
                continue
            cfg = BacktestConfig(
                variant=var,
                z_entry=rcfg.signals["z_entry"],
                z_exit=rcfg.signals["z_exit"],
                z_stop=rcfg.signals["z_stop"],
                time_stop_half_lives=rcfg.signals["time_stop_half_lives"],
                max_groups=max_groups,
                trade_bars=rcfg.trade_bars[interval],
                bars_per_year=bars_per_year,
                min_edge_multiple=min_edge_multiple,
                max_group_size=max_size,
                gross_leverage=gross_leverage,
            )
            res = run_backtest(
                panel, selections, cm, sub, spreads, cfg, start_bar, inverse_map=inv_map
            )
            tag = f"{acc}__{var}"
            res.equity.to_frame().join(res.benchmark).to_parquet(out_dir / f"equity_{tag}.parquet")
            res.trades.to_parquet(out_dir / f"trades_{tag}.parquet", index=False)
            rows.append({"account": acc, "variant": var, **params, **res.stats})
            console.print(
                f"{tag}: {res.stats['n_trades']} trades, total {res.stats['total_return']:+.1%}, "
                f"monthly mean {res.stats['monthly_mean']:+.2%}, costs £{res.stats['total_costs_gbp']:,.0f} "
                f"(financing £{res.stats['financing_gbp']:,.0f})"
            )
    summary = pd.DataFrame(rows)
    summary.to_csv(out_dir / "summary.csv", index=False)
    console.print(summary.to_string())


@app.command()
def report(interval: str = typer.Option("1D"), tier: str = typer.Option("lse_etf")) -> None:
    """Bootstrap confidence intervals and the attainability report for completed backtests."""
    import pandas as pd

    from cointisa.report.attainability import analyse_equity, write_report
    from cointisa.runid import run_dir

    rcfg = load_research()
    rd = run_dir()
    rows = []
    bt_dirs = sorted(rd.glob("backtest_*"))
    # every account x variant x parameter set in this run counts as a trial for the deflated Sharpe
    n_trials_total = sum(len(list(d.glob("equity_*.parquet"))) for d in bt_dirs)
    for d in bt_dirs:
        parts = d.name.split("_")
        iv, tr = parts[1], "_".join(parts[2:4])
        params = json.loads((d / "params.json").read_text()) if (d / "params.json").exists() else {}
        summary = pd.read_csv(d / "summary.csv") if (d / "summary.csv").exists() else pd.DataFrame()
        n_trials = max(n_trials_total, 1)
        for eqf in sorted(d.glob("equity_*.parquet")):
            tag = eqf.stem[len("equity_") :]
            acc, var = tag.split("__", 1)
            eq = pd.read_parquet(eqf)
            a = analyse_equity(
                eq["equity"],
                eq["benchmark"],
                rcfg.target["monthly_return_min"],
                rcfg.bootstrap,
                rcfg.seed,
                n_trials,
            )
            extra = {}
            if not summary.empty:
                m = summary[(summary["account"] == acc) & (summary["variant"] == var)]
                if len(m):
                    extra = {
                        "n_trades": int(m["n_trades"].iloc[0]),
                        "total_costs_gbp": float(m["total_costs_gbp"].iloc[0]),
                        "financing_gbp": float(m["financing_gbp"].iloc[0])
                        if "financing_gbp" in m
                        else 0.0,
                        "beta_vs_benchmark": float(m["beta_vs_benchmark"].iloc[0]),
                        "alpha_ann_vs_benchmark": float(m["alpha_ann_vs_benchmark"].iloc[0]),
                        "max_drawdown": float(m["max_drawdown"].iloc[0]),
                    }
            rows.append(
                {"account": acc, "variant": var, "interval": iv, "tier": tr, **params, **a, **extra}
            )
    table = pd.DataFrame(rows)
    table.to_csv(rd / "attainability.csv", index=False)
    notes = [
        "Johansen trace/max-eigenvalue tests on log GBP prices, constant in the cointegrating relation, BIC lags.",
        f"Benjamini-Hochberg FDR (q={rcfg.multiple_testing['q']:.2f}) across all groups tested in each formation window.",
        "Selection at each roll uses only data before the trading start; the hedge vector and z-score "
        "normalisation are fixed from the formation window.",
        "Long-only variants: A basket rotation, B cheap-leg only, C inverse-ETF leg. Benchmark is the "
        "equal-weight hold of all selected members.",
        "Costs per fill: half-spread (Corwin-Schultz estimate with floors), slippage, FX, stamp duty, PTM "
        "levy, fixed dealing fees (HL), whole-share rounding and next-bar fills for the manual account.",
        f"Monthly return CIs: stationary block bootstrap ({rcfg.bootstrap['n_resamples']} resamples, mean block {rcfg.bootstrap['mean_block_length_months']} months).",
        "Deflated Sharpe probability corrects the monthly Sharpe for the number of account/variant trials.",
    ]
    meta = json.loads((rd / "run.json").read_text())
    write_report(
        table,
        rd / "attainability.md",
        rcfg.target["monthly_return_min"],
        rcfg.target["monthly_return_max"],
        meta,
        notes,
    )
    console.print((rd / "attainability.md").read_text())


@app.command()
def signals(
    interval: str = typer.Option("1D"),
    tier: str = typer.Option("lse_etf"),
    variant: str = typer.Option("B_cheap_leg_only"),
    judge_backend: str = typer.Option("rules"),
) -> None:
    """Print today's eligible groups, z-scores and target weights (what the bot would do)."""
    import pandas as pd

    from cointisa.backtest.prepare import build_selections, inverse_etf_map
    from cointisa.data.panel import load_close_panel, load_seed_instruments, seed_path_for_tier
    from cointisa.judge.registry import make_judge
    from cointisa.runid import run_dir
    from cointisa.signals.live import latest_signals

    rcfg = load_research()
    insts = load_seed_instruments(seed_path_for_tier(tier))
    screen_df = pd.read_parquet(run_dir() / f"screen_{interval}_{tier}.parquet")
    needed = sorted({s for g in screen_df["group"] for s in g.split("|")})
    inv_map = inverse_etf_map(insts)
    sub = {k: insts[k] for k in needed + list(inv_map.values()) if k in insts}
    panel = load_close_panel(rcfg.as_of, interval, sub, min_rows=50)
    sel = build_selections(
        screen_df,
        panel,
        insts,
        make_judge(judge_backend),
        rcfg.judge["gate_probability"],
        rcfg,
        interval,
    )
    sigs = latest_signals(
        panel,
        sel,
        variant,
        sub,
        rcfg.signals["z_entry"],
        rcfg.signals["z_exit"],
        rcfg.signals["z_stop"],
        inv_map,
    )
    rows = [
        {
            "group": s.group,
            "z": round(s.z, 2),
            "half_life": round(s.half_life, 1),
            "state": s.state,
            "edge_pct": f"{s.expected_edge_pct:.2%}",
            "targets": {k: round(v, 2) for k, v in s.targets.items() if v},
        }
        for s in sigs
    ]
    console.print(
        f"as of {panel.index[-1].date()} ({len(sigs)} eligible groups, variant {variant})"
    )
    console.print(pd.DataFrame(rows).to_string() if rows else "no eligible groups")


@app.command()
def paper_trade(
    interval: str = typer.Option("1D"),
    tier: str = typer.Option("lse_etf"),
    variant: str = typer.Option("B_cheap_leg_only"),
    max_groups: int = typer.Option(5),
    dry_run: bool = typer.Option(True, help="Print orders without sending"),
    live: bool = typer.Option(False, help="Required flag to trade the live environment"),
) -> None:
    """Turn today's signals into Trading 212 market orders (demo by default, dry-run by default)."""
    import pandas as pd

    from cointisa.backtest.prepare import build_selections, inverse_etf_map
    from cointisa.data.panel import load_close_panel, load_seed_instruments, seed_path_for_tier
    from cointisa.exec.t212_bot import OrderIntent, T212Bot
    from cointisa.judge.registry import make_judge
    from cointisa.runid import run_dir
    from cointisa.signals.live import latest_signals

    rcfg = load_research()
    insts = load_seed_instruments(seed_path_for_tier(tier))
    screen_df = pd.read_parquet(run_dir() / f"screen_{interval}_{tier}.parquet")
    needed = sorted({s for g in screen_df["group"] for s in g.split("|")})
    inv_map = inverse_etf_map(insts)
    sub = {k: insts[k] for k in needed + list(inv_map.values()) if k in insts}
    panel = load_close_panel(rcfg.as_of, interval, sub, min_rows=50)
    sel = build_selections(
        screen_df, panel, insts, make_judge("rules"), rcfg.judge["gate_probability"], rcfg, interval
    )
    sigs = latest_signals(
        panel,
        sel,
        variant,
        sub,
        rcfg.signals["z_entry"],
        rcfg.signals["z_exit"],
        rcfg.signals["z_stop"],
        inv_map,
    )[:max_groups]
    bot = T212Bot("t212_isa", str(panel.index[-1].date()), live=live)
    summary = bot.client.account_summary()
    cash = (
        float(summary["cash"]["availableToTrade"])
        if isinstance(summary.get("cash"), dict)
        else float(summary.get("totalValue", 0))
    )
    equity = float(summary.get("totalValue", cash))
    held = bot.positions()
    t212_tickers = {i.symbol: i.t212_ticker for i in insts.values() if i.t212_ticker}
    console.print(
        f"{bot.env}: equity £{equity:,.0f}, cash £{cash:,.0f}, {len(held)} positions, {len(sigs)} groups"
    )
    slice_gbp = equity / max_groups
    last = panel.iloc[-1]
    for s in sigs:
        for sym, w in s.targets.items():
            ticker = t212_tickers.get(sym) or insts[sym].yfinance.replace(
                ".L", "l_EQ"
            )  # fallback guess; verify via t212-cache
            intent = OrderIntent(
                group=s.group,
                symbol=sym,
                t212_ticker=ticker,
                target_gbp=slice_gbp * w,
                current_qty=float(held.get(ticker, 0.0)),
                price=float(last[sym]),
                reason=f"state {s.state} z {s.z:+.2f}",
            )
            bot.place(intent, dry_run=dry_run)


@app.command()
def hl_report(
    interval: str = typer.Option("1D"),
    tier: str = typer.Option("lse_etf"),
    variant: str = typer.Option("B_cheap_leg_only"),
    max_groups: int = typer.Option(8),
    capital_gbp: float = typer.Option(0.0, help="Override SIPP capital (default from costs.yaml)"),
) -> None:
    """Write the manual trade list for the HL SIPP from today's signals (whole shares, fee-adjusted)."""
    import pandas as pd

    from cointisa.backtest.prepare import build_selections, inverse_etf_map
    from cointisa.costs.model import CostModel
    from cointisa.data.panel import load_close_panel, load_seed_instruments, seed_path_for_tier
    from cointisa.exec.hl_report import write_hl_report
    from cointisa.judge.registry import make_judge
    from cointisa.runid import run_dir
    from cointisa.signals.live import latest_signals

    rcfg, ccfg = load_research(), load_costs()
    cm = CostModel(ccfg, "hl_sipp")
    capital = capital_gbp or cm.acc.capital_gbp
    insts = load_seed_instruments(seed_path_for_tier(tier))
    screen_df = pd.read_parquet(run_dir() / f"screen_{interval}_{tier}.parquet")
    needed = sorted({s for g in screen_df["group"] for s in g.split("|")})
    inv_map = inverse_etf_map(insts)
    sub = {k: insts[k] for k in needed + list(inv_map.values()) if k in insts}
    panel = load_close_panel(rcfg.as_of, interval, sub, min_rows=50)
    sel = build_selections(
        screen_df, panel, insts, make_judge("rules"), rcfg.judge["gate_probability"], rcfg, interval
    )
    sigs = latest_signals(
        panel,
        sel,
        variant,
        sub,
        rcfg.signals["z_entry"],
        rcfg.signals["z_exit"],
        rcfg.signals["z_stop"],
        inv_map,
    )[:max_groups]
    last = panel.iloc[-1]
    rows = []
    for s in sigs:
        if s.state == 0:
            continue
        for sym, w in s.targets.items():
            if w <= 0:
                continue
            price = float(last[sym])
            shares = cm.round_quantity(capital / max_groups * w / price)
            if shares <= 0:
                continue
            rows.append(
                {
                    "group": s.group,
                    "symbol": sym,
                    "name": insts[sym].name,
                    "side": "BUY",
                    "shares": int(shares),
                    "price_gbp": price,
                    "notional_gbp": shares * price,
                    "z": round(s.z, 2),
                    "half_life": round(s.half_life, 1),
                    "expected_edge_pct": s.expected_edge_pct,
                    "reason": f"state {s.state}",
                }
            )
    out = write_hl_report(
        pd.DataFrame(rows), str(panel.index[-1].date()), run_dir() / "hl_reports", cm.fixed_fee()
    )
    console.print(out.read_text())

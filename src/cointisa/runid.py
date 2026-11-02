"""Run identity: SHA-256 over the research and universe configuration (which include `as_of`).

The data manifest is not part of the id, so adding snapshots for a new tier does not orphan
existing results; instead every `run_dir()` call records the manifest hash seen, and each screen
output stores the hashes of the exact snapshots it consumed (`stage_manifest`). Account costs are
excluded too: each backtest folder carries a parameter hash that includes `costs_hash()`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cointisa.config import config_hash, load_costs, load_research, load_universe
from cointisa.data.manifest import Manifest
from cointisa.paths import RESULTS_DIR


def run_id() -> str:
    h = hashlib.sha256()
    h.update(config_hash(load_research(), load_universe()).encode())
    return h.hexdigest()[:16]


def costs_hash() -> str:
    return config_hash(load_costs())[:12]


def run_dir(create: bool = True) -> Path:
    d = RESULTS_DIR / run_id()
    if create:
        d.mkdir(parents=True, exist_ok=True)
        meta = d / "run.json"
        mh = Manifest().content_hash()
        if meta.exists():
            data = json.loads(meta.read_text())
            hist = data.setdefault("manifest_hashes", [data.get("manifest_hash", mh)])
            if mh not in hist:
                hist.append(mh)
                data["manifest_hash"] = mh
                meta.write_text(json.dumps(data, indent=1))
        else:
            meta.write_text(
                json.dumps(
                    {
                        "run_id": run_id(),
                        "config_hash": config_hash(load_research(), load_universe()),
                        "manifest_hash": mh,
                        "manifest_hashes": [mh],
                        "as_of": load_research().as_of,
                    },
                    indent=1,
                )
            )
    return d


def stage_manifest(symbols: list[str], as_of: str, interval: str, source: str = "yfinance") -> dict:
    """Hashes of the snapshot files a stage consumed, for its sidecar JSON."""
    man = Manifest()
    prefix = f"snapshots/{as_of}/{source}/"
    used = {
        v["symbol"]: v["sha256"]
        for k, v in man.entries.items()
        if k.startswith(prefix) and v.get("interval") == interval and v["symbol"] in set(symbols)
    }
    h = hashlib.sha256()
    for s in sorted(used):
        h.update(f"{s}:{used[s]}".encode())
    return {"n_symbols": len(used), "hash": h.hexdigest()[:16], "files": used}

"""Run identity: SHA-256 over research + costs + universe config and the data manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cointisa.config import config_hash, load_costs, load_research, load_universe
from cointisa.data.manifest import Manifest
from cointisa.paths import RESULTS_DIR


def run_id() -> str:
    h = hashlib.sha256()
    h.update(config_hash(load_research(), load_costs(), load_universe()).encode())
    h.update(Manifest().content_hash().encode())
    return h.hexdigest()[:16]


def run_dir(create: bool = True) -> Path:
    d = RESULTS_DIR / run_id()
    if create:
        d.mkdir(parents=True, exist_ok=True)
        meta = d / "run.json"
        if not meta.exists():
            meta.write_text(
                json.dumps(
                    {
                        "run_id": run_id(),
                        "config_hash": config_hash(load_research(), load_costs(), load_universe()),
                        "manifest_hash": Manifest().content_hash(),
                        "as_of": load_research().as_of,
                    },
                    indent=1,
                )
            )
    return d

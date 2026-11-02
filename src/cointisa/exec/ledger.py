"""Idempotent client-side order ledger. Every intended order gets a deterministic client id derived
from (date, group, symbol, target); re-running the bot on the same day never duplicates an order."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from cointisa.paths import DATA_DIR

LEDGER_DIR = DATA_DIR / "ledger"


def client_order_id(as_of: str, account: str, group: str, symbol: str, target_gbp: float) -> str:
    raw = f"{as_of}|{account}|{group}|{symbol}|{round(target_gbp, 2)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class Ledger:
    def __init__(self, account: str, env: str, path: Path | None = None):
        self.path = path or LEDGER_DIR / f"{env}_{account}.jsonl"
        self.rows: dict[str, dict] = {}
        if self.path.exists():
            with open(self.path) as fh:
                for line in fh:
                    if line.strip():
                        r = json.loads(line)
                        self.rows[r["client_id"]] = r

    def seen(self, client_id: str) -> bool:
        return client_id in self.rows

    def record(self, client_id: str, **fields) -> None:
        row = {"client_id": client_id, "recorded_at": datetime.now(UTC).isoformat(), **fields}
        self.rows[client_id] = row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")

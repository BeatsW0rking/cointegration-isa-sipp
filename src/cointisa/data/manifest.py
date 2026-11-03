"""Hash manifest for data snapshots. data/manifest.json is committed; the parquet files are not."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cointisa.paths import DATA_DIR, MANIFEST_PATH


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Manifest:
    """Maps repo-relative snapshot paths to their hash and provenance."""

    def __init__(self, path: Path = MANIFEST_PATH):
        self.path = path
        self.entries: dict[str, dict[str, Any]] = {}
        if path.exists():
            with open(path) as fh:
                self.entries = json.load(fh).get("files", {})

    @staticmethod
    def _rel(path: Path) -> str:
        return str(path.resolve().relative_to(DATA_DIR.resolve())).replace("\\", "/")

    def record(self, path: Path, **meta: Any) -> dict[str, Any]:
        entry = {
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "recorded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            **meta,
        }
        self.entries[self._rel(path)] = entry
        return entry

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"files": dict(sorted(self.entries.items()))}
        with open(self.path, "w") as fh:
            json.dump(payload, fh, indent=1, sort_keys=True)
            fh.write("\n")

    def verify(self) -> tuple[list[str], list[str], list[str]]:
        """Return (ok, mismatched, missing) relative paths."""
        ok, bad, missing = [], [], []
        for rel, entry in self.entries.items():
            p = DATA_DIR / rel
            if not p.exists():
                missing.append(rel)
            elif sha256_file(p) != entry["sha256"]:
                bad.append(rel)
            else:
                ok.append(rel)
        return ok, bad, missing

    def content_hash(self) -> str:
        """Hash of all recorded file hashes; part of the run id."""
        h = hashlib.sha256()
        for rel in sorted(self.entries):
            h.update(rel.encode())
            h.update(self.entries[rel]["sha256"].encode())
        return h.hexdigest()

    def for_as_of(self, as_of: str) -> dict[str, dict[str, Any]]:
        prefix = f"snapshots/{as_of}/"
        return {k: v for k, v in self.entries.items() if k.startswith(prefix)}

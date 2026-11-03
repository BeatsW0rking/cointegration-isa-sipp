"""Economic-plausibility judge: does a statistically cointegrated group have a durable reason to
co-move? Backends return a calibrated probability; a gate threshold decides whether to trade.

All backends share one interface and one on-disk cache (data/judge_cache/<backend>.jsonl, committed)
keyed by a content hash of the group's metadata, so results are reproducible and re-runs are free.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path

from cointisa.instruments import Instrument
from cointisa.paths import DATA_DIR

JUDGE_CACHE_DIR = DATA_DIR / "judge_cache"


@dataclass
class JudgeResult:
    prob: float  # P(durable economic linkage) in [0, 1]
    tags: list[str] = field(default_factory=list)  # e.g. ["same_benchmark", "fx_share_class"]
    rationale: str = ""
    backend: str = ""
    cached: bool = False
    raw: dict = field(default_factory=dict)


def group_key(instruments: list[Instrument]) -> str:
    payload = [
        {
            "symbol": i.symbol,
            "name": i.name,
            "currency": i.currency,
            "type": i.type,
            "isin": i.isin,
            "leverage": i.leverage,
        }
        for i in sorted(instruments, key=lambda x: x.symbol)
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]


def describe_group(instruments: list[Instrument]) -> str:
    lines = []
    for i in sorted(instruments, key=lambda x: x.symbol):
        extra = []
        if i.isin:
            extra.append(f"ISIN {i.isin}")
        if i.leverage != 1.0:
            extra.append(f"leverage {i.leverage:g}x")
        if i.hedged_to:
            extra.append(f"hedged to {i.hedged_to}")
        tail = f" ({', '.join(extra)})" if extra else ""
        lines.append(f"- {i.symbol}: {i.name}; type {i.type}; quoted in {i.currency}{tail}")
    return "\n".join(lines)


class PlausibilityJudge(ABC):
    name: str = "base"

    def __init__(self, cache_dir: Path = JUDGE_CACHE_DIR):
        self.cache_path = cache_dir / f"{self.name}.jsonl"
        self._cache: dict[str, dict] = {}
        if self.cache_path.exists():
            with open(self.cache_path) as fh:
                for line in fh:
                    if line.strip():
                        rec = json.loads(line)
                        self._cache[rec["key"]] = rec["result"]

    def score(self, instruments: list[Instrument]) -> JudgeResult:
        key = group_key(instruments)
        if key in self._cache:
            r = JudgeResult(**self._cache[key])
            r.cached = True
            return r
        result = self._score(instruments)
        result.backend = self.name
        result.cached = False
        self._cache[key] = asdict(result)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "a") as fh:
            fh.write(json.dumps({"key": key, "result": asdict(result)}, sort_keys=True) + "\n")
        return result

    @abstractmethod
    def _score(self, instruments: list[Instrument]) -> JudgeResult: ...

    @property
    def available(self) -> bool:
        return True

"""TypeSafe Jev (System One) backend. Raw HTTP against https://api.typesafe.ai/v1/systemone.

Request: {"state": <text>, "model": "jev-latest", "questions": {id: {"type": "noul",
"instructions": ..., "criteria": {"true": ..., "false": ...}}}}. A Noul answer is P(yes) in [0, 1].
Several atomic questions are asked and combined in code, as the TypeSafe docs recommend.
Activates when TYPESAFE_API_KEY is set. Docs snapshot fetched 2026-11-02.
"""

from __future__ import annotations

import os

import httpx

from cointisa.instruments import Instrument
from cointisa.judge.base import JudgeResult, PlausibilityJudge, describe_group

ENDPOINT = "https://api.typesafe.ai/v1/systemone"

QUESTIONS = {
    "same_underlying": {
        "type": "noul",
        "instructions": "All listed instruments track the same underlying index, commodity or company "
        "(differences only in issuer, share class, currency, hedging, distribution policy, or "
        "inverse/leverage).",
        "criteria": {
            "true": "Same benchmark/commodity/company for every member",
            "false": "At least one member tracks something different",
        },
    },
    "heavy_overlap": {
        "type": "noul",
        "instructions": "The instruments' underlying holdings overlap heavily (most of the weight is in "
        "the same securities), even if the benchmarks differ.",
    },
    "economic_mechanism": {
        "type": "noul",
        "instructions": "There is a well-known economic mechanism (arbitrage, shared cash flows, "
        "substitution, supply chain) that should keep these instruments' prices tied together over "
        "years, not just correlated in the short run.",
    },
    "unrelated": {
        "type": "noul",
        "instructions": "These instruments are unrelated: different regions, asset classes or themes "
        "with no structural link; any statistical co-movement is likely coincidental.",
    },
}


class JevJudge(PlausibilityJudge):
    name = "jev"

    def __init__(self, model: str = "jev-latest", **kw):
        super().__init__(**kw)
        self.model = model

    @property
    def available(self) -> bool:
        return bool(os.environ.get("TYPESAFE_API_KEY"))

    def _score(self, instruments: list[Instrument]) -> JudgeResult:
        key = os.environ["TYPESAFE_API_KEY"]
        body = {"state": describe_group(instruments), "model": self.model, "questions": QUESTIONS}
        r = httpx.post(
            ENDPOINT,
            json=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=30.0,
        )
        r.raise_for_status()
        ans = {k: float(v["noul"]) for k, v in r.json()["answers"].items()}
        # Combine atomic answers: strongest structural signal wins, penalised by "unrelated".
        structural = max(
            ans["same_underlying"], 0.7 * ans["heavy_overlap"], 0.6 * ans["economic_mechanism"]
        )
        prob = max(0.0, min(1.0, structural * (1.0 - 0.8 * ans["unrelated"])))
        tags = [k for k, v in ans.items() if v >= 0.7]
        return JudgeResult(prob=prob, tags=tags, rationale="jev noul combination", raw=ans)

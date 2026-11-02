"""Claude-based plausibility judge with structured JSON output.

Model: claude-opus-5-5 by default (override with COINTISA_JUDGE_MODEL). Thinking stays on (adaptive)
with low effort; the question is a quick, well-scoped judgment. Server-side refusal fallbacks are
enabled by default so a policy decline is retried on a fallback model inside the same call.
"""

from __future__ import annotations

import json
import os

from pydantic import BaseModel, Field

from cointisa.instruments import Instrument
from cointisa.judge.base import JudgeResult, PlausibilityJudge, describe_group

SYSTEM = """You assess whether a group of exchange-traded instruments has a durable economic reason
to move together, so that a statistically detected cointegration is unlikely to be spurious.

Strong reasons (probability 0.85-0.99): same underlying index or commodity (different issuers,
share classes, currencies, hedged vs unhedged, distributing vs accumulating), dual listings or
depositary receipts of the same company, an inverse or leveraged product and its underlying.
Moderate reasons (0.4-0.7): heavy constituent overlap (S&P 500 vs MSCI USA vs MSCI World), the same
narrow sector or commodity complex (gold vs silver, oil vs energy equities), same issuer cash-like
funds. Weak or none (0.02-0.2): different regions, asset classes or themes with no mechanism.

Be calibrated: the probability is your belief that the relationship will persist out of sample.
Answer only with the JSON object."""


class JudgeAnswer(BaseModel):
    probability: float = Field(ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list, max_length=6)
    rationale: str = Field(max_length=400)


SCHEMA = {
    "type": "object",
    "properties": {
        "probability": {"type": "number", "minimum": 0, "maximum": 1},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "rationale": {"type": "string", "maxLength": 400},
    },
    "required": ["probability", "tags", "rationale"],
    "additionalProperties": False,
}


class ClaudeJudge(PlausibilityJudge):
    name = "claude"

    def __init__(self, model: str | None = None, **kw):
        super().__init__(**kw)
        self.model = model or os.environ.get("COINTISA_JUDGE_MODEL", "claude-opus-5-5")
        self._client = None

    @property
    def available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def _score(self, instruments: list[Instrument]) -> JudgeResult:
        client = self._get_client()
        prompt = (
            "Instruments:\n"
            + describe_group(instruments)
            + "\n\nWhat is the probability that these instruments share a durable economic linkage "
            "that would make their prices cointegrated out of sample?"
        )
        kwargs = dict(
            model=self.model,
            max_tokens=2000,
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        )
        try:
            resp = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
            )
        except TypeError:
            # SDK without the fallbacks parameter: plain call
            resp = client.messages.create(**kwargs)
        if resp.stop_reason == "refusal":
            return JudgeResult(prob=0.5, tags=["refusal"], rationale="model declined", raw={})
        text = next(b.text for b in resp.content if b.type == "text")
        ans = JudgeAnswer.model_validate(json.loads(text))
        return JudgeResult(
            prob=ans.probability,
            tags=ans.tags,
            rationale=ans.rationale,
            raw={
                "model": resp.model,
                "usage": resp.usage.to_dict() if hasattr(resp.usage, "to_dict") else {},
            },
        )

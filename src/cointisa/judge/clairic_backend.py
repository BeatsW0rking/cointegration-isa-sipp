"""Cloudflare Workers AI Clairic (System One extraction/estimation model) backend.

REST: POST https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/clairic
with a Bearer API token. Clairic returns typed values with confidence; we ask for a single numeric
estimate in [0, 1]. The exact input schema could not be verified in this session
(developers.cloudflare.com is not in the allowed domains) and is marked VERIFY below.
Activates when CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are set.
"""

from __future__ import annotations

import os

import httpx

from cointisa.instruments import Instrument
from cointisa.judge.base import JudgeResult, PlausibilityJudge, describe_group

MODEL = "@cf/cloudflare/clairic"


class ClairicJudge(PlausibilityJudge):
    name = "clairic"

    @property
    def available(self) -> bool:
        return bool(
            os.environ.get("CLOUDFLARE_ACCOUNT_ID") and os.environ.get("CLOUDFLARE_API_TOKEN")
        )

    def _score(self, instruments: list[Instrument]) -> JudgeResult:
        acct = os.environ["CLOUDFLARE_ACCOUNT_ID"]
        token = os.environ["CLOUDFLARE_API_TOKEN"]
        url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{MODEL}"
        # VERIFY against the Clairic model card: field names for the extraction target and output.
        body = {
            "input": describe_group(instruments),
            "extract": [
                {
                    "name": "linkage_probability",
                    "type": "number",
                    "description": "Probability (0 to 1) that these instruments share a durable "
                    "economic linkage making their prices cointegrated out of sample.",
                }
            ],
        }
        r = httpx.post(url, json=body, headers={"Authorization": f"Bearer {token}"}, timeout=30.0)
        r.raise_for_status()
        payload = r.json()
        result = payload.get("result", payload)
        value, conf = None, None
        # Tolerate a few plausible response layouts until the schema is verified.
        for cand in (result.get("linkage_probability"), *(result.get("values") or {}).values()):
            if isinstance(cand, dict) and "value" in cand:
                value, conf = cand["value"], cand.get("confidence")
                break
            if isinstance(cand, int | float):
                value = cand
                break
        if value is None:
            raise RuntimeError(f"unrecognised Clairic response: {str(payload)[:300]}")
        prob = max(0.0, min(1.0, float(value)))
        return JudgeResult(
            prob=prob, tags=[], rationale="clairic estimate", raw={"confidence": conf}
        )

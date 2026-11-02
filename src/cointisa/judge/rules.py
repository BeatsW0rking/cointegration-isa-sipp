"""Deterministic taxonomy judge. No model, fully reproducible; the baseline every other backend is
compared against. Probabilities are priors chosen by hand and documented here, not fitted."""

from __future__ import annotations

import re

from cointisa.instruments import Instrument
from cointisa.judge.base import JudgeResult, PlausibilityJudge

# Benchmark families: regex -> canonical key. Order matters (more specific first).
BENCHMARKS: list[tuple[str, str]] = [
    (r"s&p\s*500\s*(equal|ew)", "sp500_equal_weight"),
    (
        r"s&p\s*500\s*(info|tech|financial|health|energy|consumer|industrial|utilit|material|comm)",
        "sp500_sector",
    ),
    (r"s&p\s*500|sp\s*500|\bspx\b", "sp500"),
    (r"nasdaq[\s-]*100|\bndx\b", "nasdaq100"),
    (r"ftse\s*100", "ftse100"),
    (r"ftse\s*250", "ftse250"),
    (r"ftse\s*all[\s-]*share", "ftse_all_share"),
    (
        r"msci\s*world\s*(small|sri|esg|quality|momentum|value|min(imum)?\s*vol)",
        "msci_world_factor",
    ),
    (r"msci\s*(acwi|all\s*country)", "msci_acwi"),
    (r"ftse\s*(all[\s-]*world|global\s*all[\s-]*cap)", "ftse_all_world"),
    (r"msci\s*world", "msci_world"),
    (r"msci\s*(em|emerging)", "msci_em"),
    (r"msci\s*europe", "msci_europe"),
    (r"msci\s*(usa|us\b)", "msci_usa"),
    (r"msci\s*japan|topix|nikkei", "japan"),
    (r"euro\s*stoxx\s*50|eurostoxx", "eurostoxx50"),
    (r"stoxx\s*(europe\s*)?600", "stoxx600"),
    (r"\bdax\b", "dax"),
    (r"\bcac\b", "cac"),
    (r"russell\s*2000", "russell2000"),
    (r"physical\s*gold|\bgold\b", "gold"),
    (r"physical\s*silver|\bsilver\b", "silver"),
    (r"brent|wti|crude\s*oil", "oil"),
    (r"natural\s*gas", "natgas"),
    (r"\bbitcoin\b|\bbtc\b", "bitcoin"),
    (r"treasury\s*(bond)?\s*(20|\d+\+?)\s*(yr|year)|20\+\s*year", "ust_long"),
    (r"treasury\s*(bond)?\s*(7-10|1-3|3-7)", "ust_mid"),
    (r"uk\s*gilt|gilts", "gilts"),
    (r"global\s*aggregate\s*bond|global\s*agg", "global_agg"),
    (r"(usd|dollar)\s*(corporate|corp)\s*bond", "usd_corp"),
    (r"high\s*yield", "high_yield"),
    (r"overnight|money\s*market|ultrashort|cash", "cash_like"),
    (r"clean\s*energy", "clean_energy"),
    (r"semiconductor", "semis"),
    (r"robotic|automation|ai\b|artificial\s*intelligence", "ai_robotics"),
    (r"world\s*energy|global\s*energy", "energy_sector"),
    (r"dividend\s*aristocrat|high\s*dividend|quality\s*dividend", "dividend"),
]
ISSUERS = [
    "ishares",
    "vanguard",
    "xtrackers",
    "amundi",
    "lyxor",
    "invesco",
    "spdr",
    "hsbc",
    "wisdomtree",
    "ubs",
    "l&g",
    "legal & general",
    "franklin",
    "jpm",
    "jpmorgan",
    "fidelity",
    "vaneck",
    "bnp",
    "ossiam",
    "first trust",
    "global x",
    "leverage shares",
    "graniteshares",
]


def benchmark_key(name: str) -> str | None:
    n = name.lower()
    for pat, key in BENCHMARKS:
        if re.search(pat, n):
            return key
    return None


def issuer_key(name: str) -> str | None:
    n = name.lower()
    for iss in ISSUERS:
        if iss in n:
            return iss
    return None


def is_hedged(name: str) -> bool:
    return bool(re.search(r"hedged", name, re.I))


class RulesJudge(PlausibilityJudge):
    name = "rules"

    def _score(self, instruments: list[Instrument]) -> JudgeResult:
        tags: list[str] = []
        benches = {benchmark_key(i.name) for i in instruments}
        issuers = {issuer_key(i.name) for i in instruments}
        hedged = [is_hedged(i.name) for i in instruments]
        ccys = {i.major_currency for i in instruments}
        inverse = any(i.leverage < 0 for i in instruments)
        leveraged = any(abs(i.leverage) != 1.0 for i in instruments)
        if leveraged:
            tags.append("leveraged_or_inverse")
        if None not in benches and len(benches) == 1:
            tags.append("same_benchmark")
            if len(ccys) > 1:
                tags.append("fx_share_class")
            if any(hedged) and not all(hedged):
                tags.append("hedged_vs_unhedged")
            if len(issuers) > 1:
                tags.append("different_issuers")
            prob = 0.95
            if "hedged_vs_unhedged" in tags or "fx_share_class" in tags:
                prob = 0.90  # cointegrated only once FX is in the system; still structural
            if inverse:
                prob = 0.85  # daily-reset path dependence weakens the link
            rationale = "All members track the same benchmark index or commodity."
        elif (
            None not in benches
            and len(benches) == 2
            and benches & {"sp500", "msci_usa", "msci_world", "msci_acwi", "ftse_all_world"}
        ):
            overlap = benches <= {
                "sp500",
                "msci_usa",
                "msci_world",
                "msci_acwi",
                "ftse_all_world",
                "nasdaq100",
            }
            prob = 0.6 if overlap else 0.3
            tags.append("overlapping_constituents" if overlap else "related_benchmarks")
            rationale = (
                "Benchmarks share a large constituent overlap."
                if overlap
                else "Related but distinct benchmarks."
            )
        elif (
            None not in benches
            and len(benches) == 2
            and ({"gold", "silver"} == benches or {"oil", "energy_sector"} == benches)
        ):
            prob = 0.5
            tags.append("economically_linked_assets")
            rationale = (
                "Distinct assets with a known economic linkage (precious metals; oil vs energy)."
            )
        elif None in benches:
            prob = 0.15
            tags.append("unclassified_member")
            rationale = "At least one member has no recognised benchmark; treat as weak prior."
        else:
            prob = 0.10
            tags.append("unrelated_benchmarks")
            rationale = (
                "Members track unrelated benchmarks; statistical cointegration is likely spurious."
            )
        return JudgeResult(
            prob=prob,
            tags=tags,
            rationale=rationale,
            raw={"benchmarks": sorted(str(b) for b in benches)},
        )

import numpy as np
import pandas as pd

from cointisa.instruments import Instrument
from cointisa.judge.rules import RulesJudge
from cointisa.report.edge_budget import edge_budget
from cointisa.screen.candidates import candidate_groups


def _stock(sym, sector, industry):
    return Instrument(
        symbol=sym,
        name=sym,
        currency="GBX",
        exchange="LSE",
        type="stock",
        country="GB",
        sector=sector,
        issuer=industry,
    )


def test_rules_judge_scores_stocks_by_industry_and_sector(tmp_path):
    j = RulesJudge(cache_dir=tmp_path)
    banks = [
        _stock("LSE:LLOY", "Finance", "Major Banks"),
        _stock("LSE:BARC", "Finance", "Major Banks"),
    ]
    fin = [
        _stock("LSE:LLOY", "Finance", "Major Banks"),
        _stock("LSE:LGEN", "Finance", "Life Insurance"),
    ]
    mixed = [
        _stock("LSE:LLOY", "Finance", "Major Banks"),
        _stock("LSE:SHEL", "Energy Minerals", "Oil"),
    ]
    assert j.score(banks).prob == 0.6 and "same_industry" in j.score(banks).tags
    assert j.score(fin).prob == 0.4
    assert j.score(mixed).prob == 0.1


def test_candidate_blocks_keep_groups_within_sector(rng):
    n = 600
    idx = pd.date_range("2022-01-03", periods=n, freq="B", tz="UTC")
    common = np.cumsum(rng.normal(0, 0.01, n))
    cols = {
        s: 100 * np.exp(common + np.cumsum(rng.normal(0, 0.003, n))) for s in ["A", "B", "C", "D"]
    }
    panel = pd.DataFrame(cols, index=idx)  # all four highly correlated
    blocks = {"A": "banks", "B": "banks", "C": "oil", "D": "oil"}
    groups, clusters = candidate_groups(
        panel, threshold=0.5, max_size=2, min_overlap=100, blocks=blocks
    )
    assert groups and all(blocks[g[0]] == blocks[g[1]] for g in groups)
    groups_nb, _ = candidate_groups(panel, threshold=0.5, max_size=2, min_overlap=100)
    assert ("A", "C") in groups_nb and ("A", "C") not in groups


def test_edge_budget_net_edge_falls_with_costs(costs_cfg):
    insts = {
        "LSE:A": Instrument(symbol="LSE:A", name="A", currency="GBP", exchange="LSE", type="etf"),
        "LSE:B": Instrument(symbol="LSE:B", name="B", currency="GBP", exchange="LSE", type="etf"),
    }
    screen = pd.DataFrame(
        {
            "group": ["LSE:A|LSE:B"] * 3,
            "size": [2] * 3,
            "pass_fdr": [True] * 3,
            "pass_quality": [True] * 3,
            "persistent": [True, False, False],
            "spread_std": [0.01] * 3,
            "half_life": [5.0] * 3,
            "form_end": [1, 2, 3],
        }
    )
    t = edge_budget(screen, insts, costs_cfg, ["t212_isa", "hl_sipp"], 2.0, 0.5, 0.5)
    row = t.iloc[0]
    assert row["gross_edge_pct"] == 0.015 and row["expected_edge_pct"] == 0.0075
    assert row["net_t212_isa"] > row["net_hl_sipp"]  # HL's fixed fee lowers the net edge

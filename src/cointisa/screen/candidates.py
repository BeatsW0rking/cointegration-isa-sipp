"""Candidate group generation. Enumerating all subsets is infeasible; we cluster first.

1. Correlation clustering of log returns (average linkage, 1 - corr distance).
2. Within each cluster, enumerate groups of size min..max, capped per cluster, ordered by mean
   pairwise correlation so the most related groups are tested first. Deterministic.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform


def return_correlation(panel: pd.DataFrame, min_overlap: int = 200) -> pd.DataFrame:
    rets = np.log(panel).diff()
    corr = rets.corr(min_periods=min_overlap)
    return corr


def cluster_symbols(corr: pd.DataFrame, threshold: float = 0.6) -> dict[int, list[str]]:
    """Average-linkage clusters where members have correlation >= threshold on average."""
    c = corr.fillna(0.0).clip(-1, 1).to_numpy().copy()
    np.fill_diagonal(c, 1.0)
    dist = 1.0 - c
    dist = (dist + dist.T) / 2
    np.fill_diagonal(dist, 0.0)
    z = linkage(squareform(dist, checks=False), method="average")
    labels = fcluster(z, t=1.0 - threshold, criterion="distance")
    out: dict[int, list[str]] = {}
    for sym, lab in zip(corr.columns, labels, strict=True):
        out.setdefault(int(lab), []).append(sym)
    return {k: sorted(v) for k, v in out.items() if len(v) >= 2}


def enumerate_groups(
    members: list[str],
    corr: pd.DataFrame,
    min_size: int = 2,
    max_size: int = 5,
    cap: int = 500,
) -> list[tuple[str, ...]]:
    """Groups within one cluster, best mean pairwise correlation first, capped."""
    members = sorted(members)
    scored: list[tuple[float, tuple[str, ...]]] = []
    for k in range(min_size, min(max_size, len(members)) + 1):
        for g in combinations(members, k):
            sub = corr.loc[list(g), list(g)].to_numpy()
            iu = np.triu_indices(k, 1)
            scored.append((float(np.nanmean(sub[iu])), g))
            if len(scored) > cap * 20:
                break
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [g for _, g in scored[:cap]]


def candidate_groups(
    panel: pd.DataFrame,
    threshold: float = 0.6,
    min_size: int = 2,
    max_size: int = 5,
    cap_per_cluster: int = 500,
) -> tuple[list[tuple[str, ...]], dict[int, list[str]]]:
    corr = return_correlation(panel)
    clusters = cluster_symbols(corr, threshold)
    groups: list[tuple[str, ...]] = []
    for _, members in sorted(clusters.items()):
        groups.extend(enumerate_groups(members, corr, min_size, max_size, cap_per_cluster))
    # de-duplicate while preserving order
    seen: set[tuple[str, ...]] = set()
    uniq = []
    for g in groups:
        if g not in seen:
            seen.add(g)
            uniq.append(g)
    return uniq, clusters

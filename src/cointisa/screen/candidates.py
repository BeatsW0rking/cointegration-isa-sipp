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
    n_neighbours: int = 6,
) -> list[tuple[str, ...]]:
    """Groups within one cluster, best mean pairwise correlation first, capped.

    Pairs: every pair in the cluster. Larger groups: for each member, subsets of its
    `n_neighbours` most correlated cluster-mates, so the count grows linearly in cluster size
    rather than combinatorially. Deterministic ordering.
    """
    members = sorted(members)
    m = len(members)
    c = corr.loc[members, members].to_numpy(dtype=float)
    c = np.nan_to_num(c, nan=0.0)
    np.fill_diagonal(c, np.nan)
    scored: dict[tuple[str, ...], float] = {}

    def score(idx: tuple[int, ...]) -> float:
        sub = c[np.ix_(idx, idx)]
        iu = np.triu_indices(len(idx), 1)
        return float(np.nanmean(sub[iu]))

    if min_size <= 2:
        for i in range(m):
            for j in range(i + 1, m):
                scored[(members[i], members[j])] = float(c[i, j])
    for k in range(max(3, min_size), min(max_size, m) + 1):
        for i in range(m):
            order = np.argsort(-np.nan_to_num(c[i], nan=-9))
            nbrs = [j for j in order if j != i][:n_neighbours]
            for combo in combinations(nbrs, k - 1):
                idx = tuple(sorted((i, *combo)))
                key = tuple(members[j] for j in idx)
                if key not in scored:
                    scored[key] = score(idx)
    ranked = sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))
    return [g for g, _ in ranked[:cap]]


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

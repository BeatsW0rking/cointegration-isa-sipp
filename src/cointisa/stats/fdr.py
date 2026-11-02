"""Multiple-testing control across many cointegration tests."""

from __future__ import annotations

import numpy as np


def benjamini_hochberg(pvalues: np.ndarray, q: float = 0.05) -> tuple[np.ndarray, np.ndarray]:
    """Return (rejected mask, adjusted p-values) under the BH procedure."""
    p = np.asarray(pvalues, float)
    n = len(p)
    if n == 0:
        return np.zeros(0, bool), np.zeros(0)
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(n) + 1)
    adj = np.minimum.accumulate(ranked[::-1])[::-1]
    adj = np.clip(adj, 0, 1)
    out_adj = np.empty(n)
    out_adj[order] = adj
    return out_adj <= q, out_adj

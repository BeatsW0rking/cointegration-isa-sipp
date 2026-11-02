"""Calibration of judge probabilities against the out-of-sample persistence label."""

from __future__ import annotations

import numpy as np
import pandas as pd


def brier_score(prob: np.ndarray, label: np.ndarray) -> float:
    p, y = np.asarray(prob, float), np.asarray(label, float)
    return float(np.mean((p - y) ** 2))


def reliability_table(prob: np.ndarray, label: np.ndarray, bins: int = 5) -> pd.DataFrame:
    p, y = np.asarray(prob, float), np.asarray(label, float)
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    rows = []
    for b in range(bins):
        m = idx == b
        rows.append(
            {
                "bin_lo": edges[b],
                "bin_hi": edges[b + 1],
                "n": int(m.sum()),
                "mean_prob": float(p[m].mean()) if m.any() else np.nan,
                "observed_rate": float(y[m].mean()) if m.any() else np.nan,
            }
        )
    return pd.DataFrame(rows)


def gate_sweep(
    prob: np.ndarray, label: np.ndarray, thresholds=(0.3, 0.5, 0.7, 0.85)
) -> pd.DataFrame:
    """Precision/recall of 'persistent' when gating on prob >= threshold."""
    p, y = np.asarray(prob, float), np.asarray(label, bool)
    rows = []
    for t in thresholds:
        sel = p >= t
        rows.append(
            {
                "threshold": t,
                "selected": int(sel.sum()),
                "precision": float(y[sel].mean()) if sel.any() else np.nan,
                "recall": float(y[sel].sum() / max(y.sum(), 1)),
            }
        )
    return pd.DataFrame(rows)

"""Spread and z-score from a fixed formation-window hedge vector."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SpreadModel:
    members: tuple[str, ...]
    beta: tuple[float, ...]  # cointegrating vector, first element 1
    mean: float  # formation-window spread mean
    std: float  # formation-window spread std
    half_life: float

    def spread(self, log_prices: np.ndarray) -> np.ndarray:
        return np.asarray(log_prices) @ np.asarray(self.beta)

    def z(self, log_prices: np.ndarray) -> np.ndarray:
        return (self.spread(log_prices) - self.mean) / self.std

    @classmethod
    def fit(cls, members, beta, formation_logp: np.ndarray, half_life: float) -> SpreadModel:
        s = np.asarray(formation_logp) @ np.asarray(beta, float)
        return cls(
            tuple(members),
            tuple(float(b) for b in beta),
            float(s.mean()),
            float(s.std(ddof=1)),
            half_life,
        )


def target_tilt(z: float, state: int, z_entry: float, z_exit: float, z_stop: float) -> int:
    """Discrete three-state signal with hysteresis.

    state +1 means 'spread is rich': favour members with negative beta (they are cheap).
    state -1 means 'spread is cheap': favour members with positive beta.
    Enter at |z| >= z_entry, exit at |z| <= z_exit, force flat at |z| >= z_stop (stop-loss).
    """
    if abs(z) >= z_stop:
        return 0
    if state == 0:
        if z >= z_entry:
            return 1
        if z <= -z_entry:
            return -1
        return 0
    if state == 1:
        return 0 if z <= z_exit else 1
    return 0 if z >= -z_exit else -1


def long_short_weights(beta: np.ndarray, state: int) -> np.ndarray:
    """Signed weights for a dollar-neutral-by-hedge-ratio long/short position; sum |w| = 1.

    For a pair with beta = (1, -b): spread = log A - b log B, so £1 of A against £b of B tracks the
    spread. State +1 (spread rich): short A, long B. State -1: long A, short B. Generalises to
    groups by sign of beta. Zeros when flat.
    """
    b = np.asarray(beta, float)
    if state == 0:
        return np.zeros_like(b)
    signed = -np.sign(b) * np.abs(b) if state == 1 else np.sign(b) * np.abs(b)
    total = np.abs(signed).sum()
    return signed / total if total > 0 else np.zeros_like(b)


def cheap_side_weights(beta: np.ndarray, state: int) -> np.ndarray:
    """Weights (sum 1) on the members that are cheap given the tilt state; zeros if flat.

    With state +1 the spread is rich: members with beta < 0 are cheap. Weight is proportional to
    |beta| so a £1 hedge-ratio-weighted basket is formed on the cheap side.
    """
    b = np.asarray(beta, float)
    if state == 0:
        return np.zeros_like(b)
    cheap = (b < 0) if state == 1 else (b > 0)
    w = np.where(cheap, np.abs(b), 0.0)
    return w / w.sum() if w.sum() > 0 else np.zeros_like(b)

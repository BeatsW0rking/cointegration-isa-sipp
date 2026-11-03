"""Today's signals: the groups eligible at the latest roll, their current z-scores and the target
weights per variant. Shared by the T212 bot and the HL manual report so both act on one truth."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from cointisa.backtest.engine import GroupSelection, OpenGroup, _targets_for_group
from cointisa.instruments import Instrument
from cointisa.signals.spread import target_tilt


@dataclass
class LiveSignal:
    group: str
    members: tuple[str, ...]
    beta: tuple[float, ...]
    z: float
    half_life: float
    state: int
    targets: dict[str, float]  # weight of the group's capital per symbol
    expected_edge_pct: float  # |z| * formation std of spread, as a log-price gap estimate


def latest_signals(
    panel: pd.DataFrame,
    selections: list[GroupSelection],
    variant: str,
    insts: dict[str, Instrument],
    z_entry: float,
    z_exit: float,
    z_stop: float,
    inverse_map: dict[str, str] | None = None,
    prior_states: dict[str, int] | None = None,
) -> list[LiveSignal]:
    """Evaluate the most recent selection on the last bar of `panel`.

    `prior_states` carries yesterday's tilt per group (hysteresis); missing means flat.
    """
    if not selections:
        return []
    latest = max(selections, key=lambda s: s.start)
    logp = np.log(panel.iloc[-1])
    out = []
    for m in latest.models:
        if any(s not in logp.index or not np.isfinite(logp[s]) for s in m.members):
            continue
        lp = np.array([logp[s] for s in m.members])
        z = float(m.z(lp))
        prev = (prior_states or {}).get("|".join(m.members), 0)
        state = target_tilt(z, prev, z_entry, z_exit, z_stop)
        og = OpenGroup(model=m, opened=0, state=state)
        targets = _targets_for_group(og, variant, inverse_map, insts)
        out.append(
            LiveSignal(
                group="|".join(m.members),
                members=m.members,
                beta=m.beta,
                z=z,
                half_life=m.half_life,
                state=state,
                targets=targets,
                expected_edge_pct=float(abs(z) * m.std),
            )
        )
    return out

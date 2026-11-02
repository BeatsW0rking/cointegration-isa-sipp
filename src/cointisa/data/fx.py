"""Currency normalisation to the base currency (GBP)."""

from __future__ import annotations

import pandas as pd

from cointisa.instruments import Instrument


def to_base_currency(
    close: pd.Series,
    inst: Instrument,
    fx: dict[str, pd.Series],
    base: str = "GBP",
) -> pd.Series:
    """Convert a close series quoted in `inst.currency` to `base`.

    `fx` maps "GBPUSD" -> series of USD per GBP (and similarly GBPEUR). Pence are scaled first.
    FX is aligned by forward-fill on the price index so bars never look into the future.
    """
    s = close * inst.quote_scale_to_major
    major = inst.major_currency
    if major == base:
        return s
    key = f"{base}{major}"
    if key not in fx:
        raise KeyError(f"no FX series {key} to convert {inst.symbol} from {major} to {base}")
    rate = fx[key].reindex(s.index.union(fx[key].index)).sort_index().ffill().reindex(s.index)
    return s / rate

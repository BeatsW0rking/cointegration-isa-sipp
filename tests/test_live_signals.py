import numpy as np
import pandas as pd

from cointisa.backtest.engine import GroupSelection
from cointisa.instruments import Instrument
from cointisa.signals.live import latest_signals
from cointisa.signals.spread import SpreadModel

INSTS = {
    "LSE:A": Instrument(symbol="LSE:A", name="A", currency="GBP", exchange="LSE", type="etf"),
    "LSE:B": Instrument(symbol="LSE:B", name="B", currency="GBP", exchange="LSE", type="etf"),
}


def test_latest_signals_tilts_toward_cheap_member():
    idx = pd.date_range("2024-01-01", periods=300, freq="B", tz="UTC")
    a = pd.Series(100.0, index=idx)
    b = pd.Series(100.0, index=idx)
    b.iloc[:250] += np.sin(np.arange(250)) * 0.5  # formation noise so std > 0
    b.iloc[-1] = 97.0  # B suddenly cheap -> spread log A - log B rich -> state +1, buy B
    panel = pd.DataFrame({"LSE:A": a, "LSE:B": b})
    model = SpreadModel.fit(
        ("LSE:A", "LSE:B"), (1.0, -1.0), np.log(panel.iloc[:250]).to_numpy(), 5.0
    )
    sigs = latest_signals(
        panel, [GroupSelection(250, [model])], "B_cheap_leg_only", INSTS, 2.0, 0.5, 100.0
    )
    assert len(sigs) == 1
    s = sigs[0]
    assert s.state == 1 and s.targets["LSE:B"] == 1.0 and s.targets["LSE:A"] == 0.0
    assert s.expected_edge_pct > 0

import json

import numpy as np
import pandas as pd

from cointisa.data import store
from cointisa.data.fx import to_base_currency
from cointisa.data.manifest import Manifest, sha256_file
from cointisa.data.yfinance_provider import resample_bars
from cointisa.instruments import Instrument


def test_parquet_roundtrip_is_deterministic(tmp_path, synthetic_bars):
    p1 = store.write_bars(synthetic_bars, tmp_path / "a.parquet")
    p2 = store.write_bars(synthetic_bars.sample(frac=1, random_state=1), tmp_path / "b.parquet")
    assert sha256_file(p1) == sha256_file(p2)  # order-independent, byte-identical
    back = store.read_bars(p1)
    pd.testing.assert_frame_equal(back, store.normalise_bars(synthetic_bars))


def test_manifest_verify(tmp_path, synthetic_bars, monkeypatch):
    import cointisa.data.manifest as m

    monkeypatch.setattr(m, "DATA_DIR", tmp_path)
    mp = tmp_path / "manifest.json"
    man = Manifest(mp)
    p = store.write_bars(synthetic_bars, tmp_path / "snapshots" / "x" / "s.parquet")
    man.record(p, source="test", symbol="X", interval="1D")
    man.save()
    assert json.load(open(mp))["files"]["snapshots/x/s.parquet"]["symbol"] == "X"
    ok, bad, missing = Manifest(mp).verify()
    assert ok == ["snapshots/x/s.parquet"] and not bad and not missing
    p.write_bytes(b"corrupt")
    _, bad, _ = Manifest(mp).verify()
    assert bad == ["snapshots/x/s.parquet"]


def test_tv_columns_payload():
    payload = {
        "t": [1, 2],
        "o": [1.0, 2.0],
        "h": [1.5, 2.5],
        "l": [0.5, 1.5],
        "c": [1.2, 2.2],
        "v": [10, 20],
    }
    bars = store.normalise_bars(store.bars_from_tv_columns(payload))
    assert list(bars.columns) == store.BAR_COLUMNS and len(bars) == 2


def test_pence_and_usd_conversion():
    idx = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    gbx = Instrument(symbol="LSE:ISF", name="x", currency="GBX", exchange="LSE", type="etf")
    usd = Instrument(symbol="LSE:CSPX", name="x", currency="USD", exchange="LSE", type="etf")
    close = pd.Series([1000.0, 1010.0, 1020.0], index=idx)
    fx = {"GBPUSD": pd.Series([1.25, 1.25, 1.30], index=idx)}
    assert np.allclose(to_base_currency(close, gbx, fx), [10.0, 10.1, 10.2])
    assert np.allclose(to_base_currency(close, usd, fx), [800.0, 808.0, 1020 / 1.3])


def test_resample_1h_to_4h():
    t = store.to_unix_seconds(pd.date_range("2024-01-02 08:00", periods=8, freq="h", tz="UTC"))
    bars = pd.DataFrame(
        {"t": t, "o": range(8), "h": range(1, 9), "l": range(8), "c": range(8), "v": [1] * 8}
    )
    r = resample_bars(bars, "4h")
    assert len(r) == 2 and r["v"].tolist() == [4, 4] and r["h"].tolist() == [4, 8]

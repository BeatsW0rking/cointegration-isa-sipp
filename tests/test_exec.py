import pandas as pd

from cointisa.exec.hl_report import write_hl_report
from cointisa.exec.ledger import Ledger, client_order_id


def test_ledger_idempotent(tmp_path):
    led = Ledger("t212_isa", "demo", path=tmp_path / "l.jsonl")
    cid = client_order_id("2026-10-31", "t212_isa", "A|B", "LSE:A", 1234.567)
    assert cid == client_order_id("2026-10-31", "t212_isa", "A|B", "LSE:A", 1234.5651)
    assert not led.seen(cid)
    led.record(cid, qty=1)
    assert Ledger("t212_isa", "demo", path=tmp_path / "l.jsonl").seen(cid)


def test_hl_report_writes_markdown(tmp_path):
    df = pd.DataFrame(
        [
            {
                "group": "LSE:A|LSE:B",
                "symbol": "LSE:A",
                "name": "A ETF",
                "side": "BUY",
                "shares": 12,
                "price_gbp": 80.0,
                "notional_gbp": 960.0,
                "z": -2.3,
                "half_life": 5.0,
                "expected_edge_pct": 0.012,
                "reason": "entry",
            }
        ]
    )
    p = write_hl_report(df, "2026-10-31", tmp_path, 6.95)
    text = p.read_text()
    assert "LSE:A" in text and "+1.20%" in text and "0.72%" in text

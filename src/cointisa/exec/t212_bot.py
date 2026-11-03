"""Trading 212 execution: turns target GBP holdings into market orders with safety rails.

Rails: demo environment unless T212_ENV=live *and* --live is passed; per-order notional cap; daily
notional cap; kill switch file (data/ledger/KILL) halts everything; idempotent client ids via the
ledger; sells never exceed the held quantity; only instruments present in the T212 instrument list.
The API supports market orders only in the live environment; sells use a negative quantity.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from cointisa.data.t212 import T212Client
from cointisa.exec.ledger import LEDGER_DIR, Ledger, client_order_id

log = logging.getLogger(__name__)
KILL_FILE = LEDGER_DIR / "KILL"


@dataclass
class OrderIntent:
    group: str
    symbol: str  # canonical
    t212_ticker: str
    target_gbp: float
    current_qty: float
    price: float  # GBP per share, latest
    reason: str


@dataclass
class BotLimits:
    max_order_gbp: float = 2000.0
    max_daily_gbp: float = 8000.0
    min_order_gbp: float = 20.0


class T212Bot:
    def __init__(
        self, account: str, as_of: str, live: bool = False, limits: BotLimits | None = None
    ):
        env = os.environ.get("T212_ENV", "demo")
        if live and env != "live":
            raise RuntimeError("--live requested but T212_ENV is not 'live'")
        if not live and env == "live":
            raise RuntimeError("T212_ENV=live but --live not passed; refusing to trade real money")
        self.env = env
        self.client = T212Client(env=env)
        self.ledger = Ledger(account, env)
        self.account = account
        self.as_of = as_of
        self.limits = limits or BotLimits()
        self.daily_sent = sum(
            abs(r.get("notional_gbp", 0.0))
            for r in self.ledger.rows.values()
            if r.get("as_of") == as_of
        )

    def check_kill(self) -> None:
        if KILL_FILE.exists():
            raise RuntimeError(f"kill switch present at {KILL_FILE}; not trading")

    def positions(self) -> dict[str, float]:
        return {
            p["instrument"]["ticker"]
            if isinstance(p.get("instrument"), dict)
            else p.get("ticker"): p["quantity"]
            for p in self.client.positions()
        }

    def place(self, intent: OrderIntent, dry_run: bool = True) -> dict | None:
        self.check_kill()
        cid = client_order_id(
            self.as_of, self.account, intent.group, intent.symbol, intent.target_gbp
        )
        if self.ledger.seen(cid):
            log.info("skip %s: already sent (%s)", intent.symbol, cid)
            return None
        delta_gbp = intent.target_gbp - intent.current_qty * intent.price
        if abs(delta_gbp) < self.limits.min_order_gbp:
            return None
        delta_gbp = max(-self.limits.max_order_gbp, min(self.limits.max_order_gbp, delta_gbp))
        if self.daily_sent + abs(delta_gbp) > self.limits.max_daily_gbp:
            log.warning("daily cap reached; skipping %s", intent.symbol)
            return None
        qty = round(delta_gbp / intent.price, 4)
        if qty < 0:
            qty = -min(abs(qty), intent.current_qty)
        if qty == 0:
            return None
        log.info(
            "%s %s %s qty=%s (~£%.0f) reason=%s",
            "DRY" if dry_run else self.env.upper(),
            "BUY" if qty > 0 else "SELL",
            intent.t212_ticker,
            qty,
            abs(delta_gbp),
            intent.reason,
        )
        resp = None
        if not dry_run:
            resp = self.client.place_market(intent.t212_ticker, qty)
        self.ledger.record(
            cid,
            as_of=self.as_of,
            symbol=intent.symbol,
            ticker=intent.t212_ticker,
            qty=qty,
            notional_gbp=delta_gbp,
            reason=intent.reason,
            dry_run=dry_run,
            order_id=(resp or {}).get("id"),
            status=(resp or {}).get("status"),
        )
        self.daily_sent += abs(delta_gbp)
        return resp

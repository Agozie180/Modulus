"""The Night Watchman - weekend / overnight gap elder.

Research (research/weekend_study.py, data Jun-Oct 2026, 87 bStocks):
the market-neutral part of a bStock's weekend on-chain drift (Fri 20:00 UTC ->
Mon 13:00 UTC) CONTINUED into Monday's regular session 59.8% of the time
(n=97, |drift|>0.5%), +49 bps average. The chain is not noise while Wall
Street sleeps; it is early price discovery. So this elder follows the
idiosyncratic drift - and never claims more than the evidence supports.
"""
from __future__ import annotations
from datetime import datetime, timezone
from .base import Elder, Opinion, clamp
from ..clients import public_bapi as pub

BASE_RATE = 0.598   # measured continuation rate (n=97)
MIN_DRIFT = 0.005


def last_us_close_ms(now: datetime) -> int:
    """Open time of the 19:00 UTC hourly candle of the most recent completed US session (EDT close 20:00 UTC)."""
    from datetime import timedelta
    d = now.astimezone(timezone.utc)
    c = d.replace(hour=19, minute=0, second=0, microsecond=0)
    if c + timedelta(hours=1) > d:
        c -= timedelta(days=1)
    while c.weekday() >= 5:
        c -= timedelta(days=1)
    return int(c.timestamp() * 1000)


def last_friday_close_ms(now: datetime) -> int:
    from datetime import timedelta
    d = now.astimezone(timezone.utc)
    days_back = (d.weekday() - 4) % 7
    fri = (d - timedelta(days=days_back)).replace(hour=19, minute=0, second=0, microsecond=0)
    if fri > d:
        fri -= timedelta(days=7)
    return int(fri.timestamp() * 1000)


class GapElder(Elder):
    name, title, prior_weight = "gap", "The Night Watchman", 1.4

    def opine(self, asset, ctx) -> Opinion:
        if ctx.get("session") == "regular":
            return self.abstain("US market open: no stale reference to exploit.")
        leg = asset.bstock
        candles = ctx.get("klines", {}).get(leg.symbol)
        if candles is None:
            candles = pub.kline(leg.address, "1h", 200)
        if not candles:
            return self.abstain("no candles")
        px = {int(c[0]): float(c[4]) for c in candles}
        target = last_us_close_ms(ctx["now"])
        anchor = max((t for t in px if t <= target), default=None)
        if not anchor:
            return self.abstain("no anchor candle")
        drift = px[max(px)] / px[anchor] - 1
        idio = drift - ctx.get("market_drift", 0.0)
        if abs(idio) < MIN_DRIFT:
            return self.abstain(f"idiosyncratic drift {idio:+.2%} below {MIN_DRIFT:.1%}", drift=drift, idio=idio)
        p = clamp(BASE_RATE + min(abs(idio), 0.03) * 0.5, 0.5, 0.66)
        d = 1 if idio > 0 else -1
        return Opinion(self.name, d, p,
                       f"{leg.symbol} drifted {drift:+.2%} on-chain since the last US close "
                       f"({idio:+.2%} vs the bStock market). Off-hours drift continued 60% of the time in our backtest.",
                       {"drift": round(drift, 5), "idio": round(idio, 5), "base_rate": BASE_RATE})

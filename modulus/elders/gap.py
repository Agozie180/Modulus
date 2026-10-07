"""The Night Watchman - knows which kind of night it is.

v1 of Modulus believed weekend drift CONTINUES (59.8%, 4 weekends of thin on-chain DEX prints).
More data killed that idea. On Binance Spot (the deepest bStock venue), 17 weekends, 858
stock-weekends, the truth is subtler and more useful:

  * The weekend token gets Monday's DIRECTION right (market level 13/17 weekends, corr 0.60)
    but its SIZE wrong: the real Monday gap is only ~0.52x the token's idiosyncratic weekend move.
  * So big idiosyncratic weekend moves OVERSHOOT. Fading |move| > 1% at Sunday 21:00 UTC won
    66% to Monday's open (+103 bps for 1-2%, +164 bps beyond 2%; 13 of 14 weekends positive).
  * On WEEKNIGHTS the opposite holds: moves are informed, fading them lost ~40 bps, so we follow
    (weakly).

Spot only: fading a weekend dump = BUY; fading a weekend pump = SELL/trim (never a short).
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from .base import Elder, Opinion, clamp
from ..clock import regime
from ..clients import spot

# measured fade win-rates by |idiosyncratic weekend move| at Sunday 21:00 UTC
FADE_P = [(0.02, 0.647), (0.01, 0.665)]
WEEKNIGHT_FOLLOW_P = 0.53
MIN_WEEKEND, MIN_WEEKNIGHT = 0.01, 0.01


def last_us_close_ms(now: datetime) -> int:
    """Open time of the 19:00 UTC candle (closes 16:00 ET, EDT) of the latest completed US session."""
    d = now.astimezone(timezone.utc)
    c = d.replace(hour=19, minute=0, second=0, microsecond=0)
    if c + timedelta(hours=1) > d:
        c -= timedelta(days=1)
    while c.weekday() >= 5:
        c -= timedelta(days=1)
    return int(c.timestamp() * 1000)


def drift_since_close(candles, now) -> float | None:
    px = {int(c[0]): float(c[4]) for c in candles}
    if not px:
        return None
    anchor = max((t for t in px if t <= last_us_close_ms(now)), default=None)
    return None if anchor is None else px[max(px)] / px[anchor] - 1


class GapElder(Elder):
    name, title, prior_weight = "gap", "The Night Watchman", 1.5

    def opine(self, asset, ctx) -> Opinion:
        r = ctx.get("regime") or regime(ctx["now"])
        if r == "regular":
            return self.abstain("US market open: the real stock is pricing itself.")
        leg = asset.bstock
        candles = ctx.get("spot", {}).get(leg.symbol)
        if candles is None:
            candles = spot.klines(leg.symbol, "1h", 120)
        drift = drift_since_close(candles or [], ctx["now"])
        if drift is None:
            return self.abstain("no Binance Spot candles")
        idio = drift - ctx.get("market_drift", 0.0)
        ev = {"drift": round(drift, 5), "idio": round(idio, 5), "regime": r}
        if r in ("dark_weekend", "dawn"):
            if abs(idio) < MIN_WEEKEND:
                return self.abstain(f"weekend idio move {idio:+.2%} is inside the noise band", **ev)
            p = next(p for th, p in FADE_P if abs(idio) >= th)
            if r == "dawn":            # futures are back: part of the overshoot is already corrected
                p = 0.5 + (p - 0.5) * 0.6
            d = -1 if idio > 0 else 1
            verb = "dumped" if idio < 0 else "pumped"
            return Opinion(self.name, d, clamp(p, 0.5, 0.68),
                           f"{leg.symbol} {verb} {idio:+.2%} vs the bStock market while Wall Street was dark. "
                           f"Weekend crowds overshoot: Monday kept only ~half of moves like this, and fading them won "
                           f"{p:.0%} across 14 weekends.", ev | {"study_p": p, "mode": "fade_overshoot"})
        if abs(idio) < MIN_WEEKNIGHT:
            return self.abstain(f"weeknight idio move {idio:+.2%} too small", **ev)
        return Opinion(self.name, 1 if idio > 0 else -1, WEEKNIGHT_FOLLOW_P,
                       f"{leg.symbol} moved {idio:+.2%} overnight with futures and Asia trading: weeknight moves are informed, "
                       f"so I lean with it (weakly).", ev | {"mode": "follow_informed"})

"""The Two Nights clock.

A bStock lives through two very different kinds of night (research/weekend_oracle.py,
research/oracle_tradable.py; 87 bStocks, Binance Spot 1h, Jun 11 - Oct 7 2026):

  WEEKNIGHT  (Mon-Thu after the close): the real world never fully stops - futures, overnight
             ATS venues, Asia. Token moves are INFORMED: fading them lost ~40 bps.
  DARK WEEKEND (Fri 20:00 UTC -> Sun 22:00 UTC): nothing anywhere prices US stocks. Only the
             token trades, on ~10x thinner books. Moves are EMOTIONAL: idiosyncratic moves >1%
             reverted ~45% by Monday's open (fade win 66%, +103..164 bps, 13 of 14 weekends).
  DAWN       (Sun 22:00 UTC -> Mon 13:30 UTC): CME equity futures reopen; the token's error
             vs. Monday's real open falls from -2% to -74% of the naive error, hour by hour.

The clock also says HOW to trade: weekend books are thin, so orders go out as limits and sizes
shrink with depth (liquidity_clock.json = median quote volume per token per hour-of-week)."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone

_HERE = os.path.dirname(__file__)
_CLOCK_PATH = os.path.join(_HERE, "..", "research", "data24", "liquidity_clock.json")


def regime(now: datetime | None = None) -> str:
    d = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    wd, h = d.weekday(), d.hour + d.minute / 60
    if (wd == 4 and h >= 20) or wd == 5 or (wd == 6 and h < 22):
        return "dark_weekend"
    if (wd == 6 and h >= 22) or (wd == 0 and h < 13.5):
        return "dawn"
    if wd < 5 and 13.5 <= h < 20:
        return "regular"
    return "weeknight"


def _clock() -> dict:
    try:
        return json.load(open(_CLOCK_PATH))
    except FileNotFoundError:
        return {}


def depth_factor(now: datetime | None = None) -> float:
    """Typical liquidity this hour relative to a regular-session hour (0..1]."""
    c = _clock()
    if not c:
        return 1.0
    d = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reg = sorted(v for k, v in c.items() if int(k[0]) < 5 and 14 <= int(k[2:]) < 20)
    ref = reg[len(reg) // 2] if reg else 1.0
    return max(0.05, min(1.0, c.get(f"{d.weekday()}-{d.hour:02d}", ref) / ref))


def execution_policy(now: datetime | None = None) -> dict:
    """How the executor must behave right now."""
    r, f = regime(now), depth_factor(now)
    return {"regime": r, "depth_factor": round(f, 3),
            "size_scale": round(max(0.25, f ** 0.5), 3),          # thin book -> smaller clip
            "order_type": "limit" if r in ("dark_weekend", "dawn") or f < 0.5 else "market",
            "max_slippage_pct": 0.5 if r == "dark_weekend" else 1.0}

"""Position sizing: fractional Kelly on the CALIBRATED probability, then hard caps.

For a symmetric bet with win prob p, Kelly f* = 2p - 1. Modulus uses a quarter of
it, scales by (1 - dissent), and clamps to the trade, daily and per-ticker limits.
A 60% call with a split council therefore risks a sliver, not the house.
"""
from __future__ import annotations
from .config import RiskLimits


def size_usd(conf: float, dissent: float, nav_usd: float, spent_today: float, held_usd: float,
             limits: RiskLimits) -> float:
    kelly = max(0.0, 2 * conf - 1) * limits.kelly_fraction * (1 - dissent)
    usd = nav_usd * kelly
    usd = min(usd, limits.max_trade_usd,
              max(0.0, limits.max_daily_usd - spent_today),
              max(0.0, nav_usd * limits.max_position_pct - held_usd))
    return round(usd, 2) if usd >= 1.0 else 0.0

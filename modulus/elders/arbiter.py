"""The Arbiter - one company, three tokens. bStocks vs Ondo vs xStocks.

Prices every representation per share (token price / sharesMultiplier). If the
bStock trades at a discount to the median of its twins beyond the cost hurdle,
it leans buy (and vice versa). A divergence above `max_oracle_divergence` is
treated as a broken feed or unadjusted split - never as free money. In the
Oct 2026 snapshot several xStocks legs sat 80-800% away from their twins
(e.g. NFLX, IBM, CRWD), exactly the trap this guard exists for.
"""
from __future__ import annotations
import statistics
from .base import Elder, Opinion, clamp
from ..config import SETTINGS

COST_HURDLE = 0.004   # ~40 bps round trip (fees + slippage on small size)


class ArbiterElder(Elder):
    name, title, prior_weight = "arbiter", "The Arbiter", 1.0

    def opine(self, asset, ctx) -> Opinion:
        b = asset.bstock.ref_price
        twins = {l.provider: l.ref_price for l in asset.twins if l.ref_price}
        if not b or not twins:
            return self.abstain("no twin to compare")
        sane = {k: v for k, v in twins.items() if abs(v / b - 1) <= SETTINGS.risk.max_oracle_divergence}
        broken = sorted(set(twins) - set(sane))
        ev = {"bstock": round(b, 4), **{k: round(v, 4) for k, v in twins.items()}, "broken_feeds": broken}
        if not sane:
            return self.abstain(f"twin feeds diverge >{SETTINGS.risk.max_oracle_divergence:.0%}: {broken}", **ev)
        fair = statistics.median(sane.values())
        prem = b / fair - 1
        ev["premium"] = round(prem, 5)
        if abs(prem) < COST_HURDLE:
            return self.abstain(f"bStock within {prem:+.2%} of twins - inside cost hurdle", **ev)
        p = clamp(0.52 + min(abs(prem), 0.03) * 3, 0.5, 0.64)
        return Opinion(self.name, -1 if prem > 0 else 1, p,
                       f"{asset.bstock.symbol} trades {prem:+.2%} vs {'/'.join(sane)} per share.", ev)

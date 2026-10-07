"""The Value Elder - slow, skeptical, fundamentals from the RWA layer.

Uses stockInfo: 52-week range position, P/E, ROE, free cash flow. Low weight:
it rarely decides a trade alone, but it brakes momentum buys at stretched
valuations and supports dips in high-quality names.
"""
from __future__ import annotations
from .base import Elder, Opinion, clamp


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


class ValueElder(Elder):
    name, title, prior_weight = "value", "The Value Elder", 0.6

    def opine(self, asset, ctx) -> Opinion:
        if asset.asset_type == 3:
            return self.abstain("ETF: no single-company fundamentals")
        si = asset.bstock.dyn.get("stockInfo") or {}
        p = asset.bstock.ref_price
        hi, lo, pe, roe = _f(si.get("priceHigh52w")), _f(si.get("priceLow52w")), _f(si.get("priceToEarnings")), _f(si.get("returnOnEquity"))
        if not (p and hi and lo and hi > lo):
            return self.abstain("no fundamentals")
        pos = (p - lo) / (hi - lo)
        ev = {"range_pos": round(pos, 3), "pe": pe, "roe": roe}
        quality = (roe or 0) > 0.15
        if pos < 0.25 and quality:
            return Opinion(self.name, 1, 0.56, f"Quality name (ROE {roe:.0%}) near 52-week low ({pos:.0%} of range).", ev)
        if pos > 0.95 and pe and pe > 60:
            return Opinion(self.name, -1, 0.55, f"At {pos:.0%} of 52-week range with P/E {pe:.0f}: stretched.", ev)
        return self.abstain(f"neutral: {pos:.0%} of 52w range, P/E {pe}", **ev)

"""The Value Elder - slow, skeptical, fundamentals from the RWA layer.

Core stockInfo fields: 52-week range position and P/E. ROE (returnOnEquity) is an
optional quality gate, applied only when the RWA layer actually provides it - it is
not a documented core RWA field. Low weight: this elder rarely decides a trade alone,
but it brakes momentum buys at stretched valuations and supports dips in high-quality
names.
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
        if asset.asset_type in (2, 3):     # REST assetType: 1 Stock, 2 Pre-IPO, 3 ETF (52w fields: Stock/ETF only)
            return self.abstain("ETF/Pre-IPO: no single-company 52-week fundamentals")
        si = asset.bstock.dyn.get("stockInfo") or {}
        p = asset.bstock.ref_price
        hi, lo, pe, roe = _f(si.get("priceHigh52w")), _f(si.get("priceLow52w")), _f(si.get("priceToEarnings")), _f(si.get("returnOnEquity"))
        if not (p and hi and lo and hi > lo):
            return self.abstain("no fundamentals")
        pos = (p - lo) / (hi - lo)
        ev = {"range_pos": round(pos, 3), "pe": pe, "roe": roe}
        quality = roe is not None and roe > 0.15
        # Guard each formatting branch on the field being present: pe/roe are Optional and the
        # reasoning must never raise when POE / 52w range / ROE data is missing (abstain instead).
        if roe is not None and pos < 0.25 and quality:
            return Opinion(self.name, 1, 0.56, f"Quality name (ROE {roe:.0%}) near 52-week low ({pos:.0%} of range).", ev)
        if pe is not None and pos > 0.95 and pe > 60:
            return Opinion(self.name, -1, 0.55, f"At {pos:.0%} of 52-week range with P/E {pe:.0f}: stretched.", ev)
        return self.abstain(f"neutral: {pos:.0%} of 52w range, P/E {pe if pe is not None else 'n/a'}", **ev)

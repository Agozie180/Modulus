"""The Sentinel - the only elder that can say NO. It never votes on direction.

Vetoes (fail-closed):
  * asset not tradable right now: statusInfo.openState == false (on-chain RFQ quotes fail with
    40369 BSTOCK_INVALID_TRADING_TIME), marketStatus == "pause" (halt / circuit breaker),
    ASSET_PAUSED (dividend, split, merger, spinoff...), MARKET_PAUSED,
    MARKET_MAINTENANCE, UNSUPPORTED
  * ASSET_LIMITED (earnings window) -> veto new entries
  * stale on-chain price (token price older than STALE_MIN)
  * broken oracle: bStock per-share price diverges from its own 52w range by >50%
  * token audit returns risk, or the audit service is unreachable (skill rule: fail-closed)
  (quote-vs-reference slippage is checked by the executor at execution time, not here)
"""
from __future__ import annotations
import time
from .base import Elder, Opinion
from ..clients import public_bapi as pub

HARD_STOP = {"ASSET_PAUSED", "MARKET_PAUSED", "MARKET_MAINTENANCE", "UNSUPPORTED", "ASSET_LIMITED"}
STALE_MIN = 180


class SentinelElder(Elder):
    name, title, prior_weight = "sentinel", "The Sentinel", 0.0

    def opine(self, asset, ctx) -> Opinion:
        leg = asset.bstock
        st = (leg.dyn.get("statusInfo") or {})
        reasons = []
        code = st.get("reasonCode")
        if code in HARD_STOP:
            reasons.append(f"{code}{': ' + st['reasonMsg'] if st.get('reasonMsg') else ''}")
        if st.get("marketStatus") == "pause" and code not in HARD_STOP:
            reasons.append("market pause (halt / circuit breaker)")
        if st.get("openState") is False and code not in HARD_STOP:
            reasons.append(f"not tradable now ({st.get('marketStatus') or code}); next open {st.get('nextOpenTime')}")
        upd = (leg.dyn.get("tokenInfo") or {}).get("tokenPriceUpdatedAt")
        if upd and (time.time() * 1000 - float(upd)) / 60000 > STALE_MIN:
            reasons.append("stale on-chain price")
        si = leg.dyn.get("stockInfo") or {}
        try:
            hi, lo, p = float(si["priceHigh52w"]), float(si["priceLow52w"]), leg.ref_price
            if p and (p > hi * 1.5 or p < lo * 0.5):
                reasons.append(f"price {p:.2f} outside 52w band {lo}-{hi}: suspect feed")
        except (KeyError, TypeError, ValueError):
            pass
        if ctx.get("audit", True):
            a = ctx.get("audits", {}).get(leg.address) or pub.token_audit(leg.address)
            if isinstance(a, dict) and a.get("error"):
                reasons.append("token audit unreachable (fail-closed)")
            elif isinstance(a, dict) and str(a.get("riskLevelEnum", "")).upper() == "HIGH":
                reasons.append(f"audit risk HIGH: {[i.get('title') for i in a.get('riskItems') or []][:3]}")
            # note: the audit currently answers isSupported=false for bStocks (see DX report)
        if reasons:
            return Opinion(self.name, 0, 0.5, "VETO - " + "; ".join(reasons), {"reasons": reasons}, veto=True)
        return Opinion(self.name, 0, 0.5, f"clear ({code or 'TRADING'})", {"status": code})

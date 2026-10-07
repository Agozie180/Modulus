"""The Whale Watcher - who is actually moving size on-chain.

Signals (all live, from token dynamic info + Agentic Wallet tracker when present):
  * order-flow imbalance  (buy - sell) / (buy + sell) across 1h / 4h / 24h windows
  * smart-money and KOL holding share (`holdersSmartMoneyPercent`, `kolHoldingPercent`)
  * Binance-wallet average cost vs price: underwater crowds sell rallies, profitable ones hold
  * concentration risk: top-10 holders share (a large exit can gap the pool)
  * baw tracker: public Smart Money (`--tag-type smy`) trade flow touching this token
"""
from __future__ import annotations
from .base import Elder, Opinion, clamp
from ..clients import public_bapi as pub


def _f(d, k):
    try:
        return float(d.get(k))
    except (TypeError, ValueError):
        return None


def imbalance(dyn: dict, win: str):
    b, s = _f(dyn, f"volume{win}Buy"), _f(dyn, f"volume{win}Sell")
    if not b or not s:
        return None, 0.0
    return (b - s) / (b + s), b + s


class WhaleElder(Elder):
    name, title, prior_weight = "whale", "The Whale Watcher", 1.1

    def opine(self, asset, ctx) -> Opinion:
        leg = asset.bstock
        dyn = ctx.get("flow", {}).get(leg.symbol) or pub.token_dynamic(leg.address) or {}
        w = {"1h": 0.5, "4h": 0.3, "24h": 0.2}
        score, used, ev = 0.0, 0.0, {}
        for win, wt in w.items():
            imb, vol = imbalance(dyn, win)
            if imb is not None:
                score += wt * imb; used += wt; ev[f"imb_{win}"] = round(imb, 3); ev[f"vol_{win}"] = round(vol)
        if not used:
            return self.abstain("no on-chain flow data")
        score /= used
        price, avg_cost = _f(dyn, "price"), _f(dyn, "bnAvgBuyPrice")
        if price and avg_cost:
            ev["crowd_pnl"] = round(price / avg_cost - 1, 4)
        sm = _f(dyn, "holdersSmartMoneyPercent") or 0
        kol = _f(dyn, "kolHoldingPercent") or 0
        top10 = _f(dyn, "top10HoldersPercentage")
        ev.update(smart_money_pct=sm, kol_pct=kol, top10_pct=top10, holders=dyn.get("holders"))
        # whales confirmed by a tracked smart-money buy/sell in the last window (baw tracker), if wired
        sm_flow = ctx.get("smart_money_flow", {}).get(leg.address.lower(), 0)
        score += 0.15 * max(-1, min(1, sm_flow))
        if abs(score) < 0.08:
            return self.abstain(f"balanced flow ({score:+.2f})", **ev)
        p = clamp(0.5 + abs(score) * 0.35, 0.5, 0.68)
        if top10 and top10 > 90:
            p = clamp(p - 0.03)  # concentrated book: flow can reverse on one wallet
        side = "buyers" if score > 0 else "sellers"
        return Opinion(self.name, 1 if score > 0 else -1, p,
                       f"On-chain {side} dominate ({score:+.0%} imbalance, 1h-weighted); "
                       f"Binance-wallet crowd is {ev.get('crowd_pnl', 0):+.1%} vs cost.", ev)

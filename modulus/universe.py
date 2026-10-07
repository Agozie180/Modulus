"""The tradable universe: every bStock on BSC, joined to its Ondo and xStocks twins."""
from __future__ import annotations
from dataclasses import dataclass, field
from .clients import public_bapi as pub
from .config import BSC, PROVIDERS


@dataclass
class Leg:
    provider: str            # bstock | ondo | xstocks
    symbol: str
    address: str
    multiplier: float
    dyn: dict = field(default_factory=dict)

    @property
    def token_price(self) -> float | None:
        try:
            return float((self.dyn.get("tokenInfo") or {})["price"])
        except (KeyError, TypeError, ValueError):
            return None

    @property
    def ref_price(self) -> float | None:
        """Per-share price: token price / sharesMultiplier (Token != Share)."""
        p = self.token_price
        m = (self.dyn.get("tokenInfo") or {}).get("sharesMultiplier") or self.multiplier
        return p / float(m) if p and m else None


@dataclass
class Asset:
    ticker: str
    asset_type: int                      # 1 stock, 3 ETF
    legs: dict[str, Leg] = field(default_factory=dict)

    @property
    def bstock(self) -> Leg:
        return self.legs["bstock"]

    @property
    def twins(self) -> list[Leg]:
        return [l for k, l in self.legs.items() if k != "bstock"]


def load_universe(with_dynamic: bool = True, tickers: list[str] | None = None) -> list[Asset]:
    lists = {t: [x for x in pub.rwa_list(t) if x.get("chainId") == BSC] for t in PROVIDERS}
    assets: dict[str, Asset] = {}
    for x in lists[3]:
        if tickers and x["ticker"] not in tickers:
            continue
        a = Asset(x["ticker"], int(x.get("assetType") or 1))
        a.legs["bstock"] = Leg("bstock", x["symbol"], x["contractAddress"], float(x.get("multiplier") or 1))
        assets[x["ticker"]] = a
    for t in (1, 2):
        for x in lists[t]:
            if x["ticker"] in assets:
                assets[x["ticker"]].legs[PROVIDERS[t]] = Leg(PROVIDERS[t], x["symbol"], x["contractAddress"],
                                                             float(x.get("multiplier") or 1))
    if with_dynamic:
        legs = [l for a in assets.values() for l in a.legs.values()]
        for leg, d in zip(legs, pub.many(lambda l: pub.rwa_dynamic(l.address), legs)):
            leg.dyn = d if isinstance(d, dict) and "error" not in d else {}
    return list(assets.values())

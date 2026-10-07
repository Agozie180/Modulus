"""Modulus agent loop.

  scan     -> load universe, convene the council for every bStock, rank verdicts
  run      -> scan + size + execute (dryrun | baw | api) + journal
  resolve  -> score past verdicts against the next price, refit calibration + elder skills
  daemon   -> session-aware loop: hourly while US is closed, every 15 min near the open
"""
from __future__ import annotations
import json, statistics, time
from datetime import datetime, timezone
from .config import SETTINGS
from .universe import load_universe
from .council import Council
from .calibration import Isotonic, brier, ece, reliability, skill
from .ledger import Ledger
from .sizing import size_usd
from .executor import Executor
from .clients import public_bapi as pub


def session_now() -> tuple[str, dict]:
    try:
        st = pub.market_status() or {}
    except Exception:
        st = {}
    ms = (st.get("marketStatus") or "").lower()
    if datetime.now(timezone.utc).weekday() >= 5 or ms == "closed":
        return "weekend" if datetime.now(timezone.utc).weekday() >= 5 else "closed", st
    return (ms or "unknown"), st


def seed_pairs(path="data/weekend_events.json"):
    """Backtest pairs for the Night Watchman so calibration is not blind on day one."""
    try:
        ev = json.load(open(path))
    except FileNotFoundError:
        return []
    by = {}
    for s, d, a, b in ev:
        by.setdefault(d, []).append((a, b))
    pairs = []
    for d, v in by.items():
        if len(v) < 10:
            continue
        ma, mb = statistics.mean(x for x, _ in v), statistics.mean(y for _, y in v)
        for a, b in v:
            idio, nxt = a - ma, b - mb
            if abs(idio) >= 0.005:
                p = min(0.66, 0.598 + min(abs(idio), 0.03) * 0.5)
                pairs.append((p, int(idio * nxt > 0)))
    return pairs


class Modulus:
    def __init__(self, settings=SETTINGS):
        self.s = settings
        self.ledger = Ledger(settings.db_path)
        pairs = self.ledger.pairs() + seed_pairs()
        self.calibrator = Isotonic.fit(pairs)
        skills = {e: skill(p) for e, p in self.ledger.elder_pairs().items() if len(p) >= 15}
        self.council = Council(calibrator=self.calibrator, skills=skills, min_confidence=settings.risk.min_confidence)
        self.executor = Executor(settings)

    def scan(self, tickers=None, audit=True):
        session, status = session_now()
        assets = load_universe(tickers=tickers)
        legs = [a.bstock for a in assets]
        klines = dict(zip([l.symbol for l in legs], pub.many(lambda l: pub.kline(l.address, "1h", 200), legs)))
        flow = dict(zip([l.symbol for l in legs], pub.many(lambda l: pub.token_dynamic(l.address), legs)))
        ctx = {"now": datetime.now(timezone.utc), "session": session, "klines": klines, "flow": flow, "audit": audit}
        # market drift = median bStock drift since anchor, so the Night Watchman trades idiosyncratic moves only
        from .elders.gap import last_us_close_ms
        anchor = last_us_close_ms(ctx["now"])
        drifts = []
        for l in legs:
            k = klines.get(l.symbol)
            if isinstance(k, list) and k:
                px = {int(c[0]): float(c[4]) for c in k}
                base = max((t for t in px if t <= anchor), default=None)
                if base:
                    drifts.append(px[max(px)] / px[base] - 1)
        ctx["market_drift"] = statistics.median(drifts) if drifts else 0.0
        verdicts = [self.council.deliberate(a, ctx) for a in assets]
        order = {"BUY": 0, "SELL": 1, "HOLD": 2, "VETO": 3}
        verdicts.sort(key=lambda v: (order[v.action], -v.confidence))
        return {"session": session, "market_status": status, "market_drift": ctx["market_drift"],
                "assets": assets, "verdicts": verdicts}

    def run(self, nav_usd=50.0, tickers=None):
        res = self.scan(tickers)
        by_ticker = {a.ticker: a for a in res["assets"]}
        acted = []
        for v in res["verdicts"]:
            price = by_ticker[v.ticker].bstock.ref_price
            vid = self.ledger.record_verdict(v, price)
            if v.action not in ("BUY", "SELL"):
                continue
            usd = size_usd(v.confidence, v.dissent, nav_usd, self.ledger.spent_today(), 0.0, self.s.risk)
            r = self.executor.execute(v, usd, by_ticker[v.ticker].bstock.token_price or price)
            self.ledger.record_order(vid, r.get("mode", self.s.executor), v.action, usd, r.get("status"), r.get("orderId", ""), r)
            acted.append((v, usd, r))
        return res, acted

    def resolve(self):
        n = 0
        for vid, addr, action, price in self.ledger.open_verdicts():
            d = pub.rwa_dynamic(addr) or {}
            try:
                self.ledger.resolve(vid, float(d["tokenInfo"]["price"]))
                n += 1
            except (KeyError, TypeError, ValueError):
                pass
        return n

    def calibration_report(self):
        pairs = self.ledger.pairs()
        seeded = seed_pairs()
        allp = pairs + seeded
        return {"live_n": len(pairs), "seed_n": len(seeded),
                "brier": round(brier(allp), 4) if allp else None, "ece": round(ece(allp), 4) if allp else None,
                "reliability": reliability(allp), "curve": self.calibrator.as_dict(),
                "elder_skill": {e: round(skill(p), 3) for e, p in self.ledger.elder_pairs().items()}}

    def daemon(self, nav_usd=50.0):
        while True:
            session, _ = session_now()
            self.resolve()
            self.run(nav_usd)
            time.sleep(900 if session in ("premarket", "regular", "postmarket") else 3600)

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


def seed_pairs(path="research/data24/tradable_rows.json"):
    """Out-of-sample-style seed for calibration: every historical dark-weekend signal the Night
    Watchman would have raised (Binance Spot, Sunday 21:00 UTC, market-neutral, |move|>1%),
    with the probability it would have claimed and whether fading to Monday's open won."""
    try:
        from .oracle import _load
        rows = _load(path)
    except FileNotFoundError:
        return []
    from .elders.gap import FADE_P
    pairs = []
    for r in rows:
        w = r["w"]
        if abs(w) < 0.01:
            continue
        p = next(p for th, p in FADE_P if abs(w) >= th)
        pairs.append((p, int((r["mo"] < 0) if w > 0 else (r["mo"] > 0))))
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
        from .clients import spot
        from .clock import regime, execution_policy
        klines = dict(zip([l.symbol for l in legs], pub.many(lambda l: spot.klines(l.symbol, "1h", 120), legs)))
        flow = dict(zip([l.symbol for l in legs], pub.many(lambda l: pub.token_dynamic(l.address), legs)))
        now = datetime.now(timezone.utc)
        ctx = {"now": now, "session": session, "regime": regime(now), "policy": execution_policy(now),
               "spot": klines, "klines": klines, "flow": flow, "audit": audit}
        # market drift = median bStock drift since anchor, so the Night Watchman trades idiosyncratic moves only
        from .elders.gap import last_us_close_ms
        anchor = last_us_close_ms(ctx["now"])
        drifts, moves = [], {}
        for l in legs:
            k = klines.get(l.symbol)
            if isinstance(k, list) and k:
                px = {int(c[0]): float(c[4]) for c in k}
                base = max((t for t in px if t <= anchor), default=None)
                if base:
                    drifts.append(px[max(px)] / px[base] - 1)
                    moves[next(a.ticker for a in assets if a.bstock is l)] = drifts[-1]
        ctx["market_drift"] = statistics.median(drifts) if drifts else 0.0
        verdicts = [self.council.deliberate(a, ctx) for a in assets]
        order = {"BUY": 0, "SELL": 1, "HOLD": 2, "VETO": 3}
        verdicts.sort(key=lambda v: (order[v.action], -v.confidence))
        return {"session": session, "regime": ctx["regime"], "policy": ctx["policy"],
                "market_status": status, "market_drift": ctx["market_drift"], "moves": moves,
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
            usd = round(usd * res["policy"]["size_scale"], 2)          # thin weekend books -> smaller clips
            if usd < 1:
                continue
            r = self.executor.execute(v, usd, by_ticker[v.ticker].bstock.token_price or price, policy=res["policy"])
            r["policy"] = res["policy"]
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
        from .clock import regime
        while True:
            session, _ = session_now()
            if self.s.executor == "baw" and regime() == "regular":
                try:   # weekend fade limits must not fill on Monday's informed tape
                    self.executor.reconcile_limits(cancel_working=True)
                except Exception:
                    pass
            self.resolve()
            self.run(nav_usd)
            time.sleep(900 if session in ("premarket", "regular", "postmarket") else 3600)

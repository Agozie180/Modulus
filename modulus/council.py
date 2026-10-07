"""The Council of Elders.

Five elders look at the same bStock from different angles. The council:
  1. collects each Opinion (direction, probability, rationale, evidence)
  2. lets the Sentinel veto - a veto ends the meeting
  3. pools the rest in log-odds space, weighted by prior weight x earned skill
  4. measures DISSENT (share of voting weight that disagrees) and shrinks confidence by it
  5. maps the raw pooled probability through the isotonic CALIBRATION curve
  6. returns one plain-English verdict a non-crypto user understands in a sentence
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from .elders import COUNCIL
from .elders.base import Opinion
from .calibration import Isotonic


def logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def sigmoid(x):
    return 1 / (1 + math.exp(-x))


@dataclass
class Verdict:
    ticker: str
    symbol: str
    address: str
    action: str                  # BUY | SELL | HOLD | VETO
    raw_p: float
    confidence: float            # calibrated
    dissent: float
    opinions: list[Opinion] = field(default_factory=list)
    headline: str = ""

    def as_dict(self):
        d = {k: v for k, v in self.__dict__.items() if k != "opinions"}
        d["opinions"] = [o.as_dict() for o in self.opinions]
        return d


class Council:
    def __init__(self, elders=None, calibrator: Isotonic | None = None, skills: dict | None = None,
                 min_confidence: float = 0.58, quorum: int = 2):
        self.elders = elders or COUNCIL
        self.cal = calibrator or Isotonic([0.5, 0.6, 0.7, 0.8], [0.5, 0.57, 0.62, 0.66])
        self.skills = skills or {}
        self.min_conf = min_confidence
        self.quorum = quorum          # no trade on a single elder's word

    def weight(self, elder) -> float:
        s = self.skills.get(elder.name)
        return elder.prior_weight * (1.0 if s is None else max(0.2, 1 + 2 * s))

    def deliberate(self, asset, ctx) -> Verdict:
        ops, weights = [], {}
        for e in self.elders:
            try:
                o = e.opine(asset, ctx)
            except Exception as ex:   # an elder failing is an abstention, never a crash
                o = e.abstain(f"error: {ex}")
            ops.append(o)
            weights[o.elder] = self.weight(e)
        leg = asset.bstock
        veto = next((o for o in ops if o.veto), None)
        if veto:
            return Verdict(asset.ticker, leg.symbol, leg.address, "VETO", 0.5, 0.0, 0.0, ops,
                           f"Stand down on {leg.symbol}: {veto.rationale[7:]}")
        votes = [o for o in ops if o.direction != 0]
        if not votes:
            return Verdict(asset.ticker, leg.symbol, leg.address, "HOLD", 0.5, 0.5, 0.0, ops,
                           f"No elder sees an edge in {leg.symbol}. Doing nothing is a position.")
        score = sum(weights[o.elder] * o.direction * logit(o.p) for o in votes)
        total_w = sum(weights[o.elder] for o in votes)
        direction = 1 if score > 0 else -1
        against = sum(weights[o.elder] for o in votes if o.direction != direction)
        dissent = against / total_w
        raw = sigmoid(abs(score) / max(1.0, math.sqrt(len(votes))))   # correlated elders: do not double count
        raw = 0.5 + (raw - 0.5) * (1 - dissent)
        conf = self.cal(raw)
        agree = len(votes) - sum(1 for o in votes if o.direction != direction)
        if conf < self.min_conf or agree < self.quorum:
            action = "HOLD"
        else:
            action = "BUY" if direction > 0 else "SELL"
        lead = max(votes, key=lambda o: weights[o.elder] * logit(o.p))
        verb = {"BUY": "Buy", "SELL": "Trim / avoid", "HOLD": "Hold"}[action]
        if action == "HOLD" and agree < self.quorum:
            verb = "Hold (no quorum)"
        head = (f"{verb} {leg.symbol} - {conf:.0%} calibrated confidence, "
                f"{agree}/{len(votes)} voting elders agree. "
                f"{lead.rationale}")
        return Verdict(asset.ticker, leg.symbol, leg.address, action, round(raw, 4), round(conf, 4),
                       round(dissent, 3), ops, head)

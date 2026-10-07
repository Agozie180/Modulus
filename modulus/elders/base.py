from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Opinion:
    elder: str
    direction: int            # +1 buy, -1 sell/avoid, 0 abstain
    p: float                  # elder's own probability that `direction` is right (0.5..0.95)
    rationale: str
    evidence: dict = field(default_factory=dict)
    veto: bool = False        # only the Sentinel may veto

    def as_dict(self):
        return self.__dict__.copy()


class Elder:
    name = "elder"
    title = ""
    prior_weight = 1.0

    def opine(self, asset, ctx) -> Opinion:  # pragma: no cover
        raise NotImplementedError

    def abstain(self, why: str, **ev) -> Opinion:
        return Opinion(self.name, 0, 0.5, why, ev)


def clamp(p: float, lo: float = 0.5, hi: float = 0.9) -> float:
    return max(lo, min(hi, p))

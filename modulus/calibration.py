"""Calibration: Modulus only trusts a confidence it has earned.

* Every verdict is journaled with its raw council probability.
* When the verdict resolves (next regular session), the outcome is recorded.
* An isotonic (pool-adjacent-violators) map raw_p -> calibrated_p is refit on the
  ledger, seeded with the weekend backtest so day one is not blind.
* Brier score and Expected Calibration Error are published on the dashboard and
  via the MCP tool `modulus_calibration`, so anyone can audit the agent's honesty.
* Elder weights adapt to each elder's Brier skill score: 1 - Brier/0.25.
"""
from __future__ import annotations
from dataclasses import dataclass


def brier(pairs: list[tuple[float, int]]) -> float:
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs) if pairs else float("nan")


def ece(pairs: list[tuple[float, int]], bins: int = 10) -> float:
    if not pairs:
        return float("nan")
    tot = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = [(p, y) for p, y in pairs if lo <= p < hi or (b == bins - 1 and p == 1)]
        if sel:
            tot += len(sel) * abs(sum(p for p, _ in sel) / len(sel) - sum(y for _, y in sel) / len(sel))
    return tot / len(pairs)


def reliability(pairs: list[tuple[float, int]], bins: int = 5, lo: float = 0.5, hi: float = 0.8):
    out = []
    w = (hi - lo) / bins
    for b in range(bins):
        a, z = lo + b * w, lo + (b + 1) * w
        sel = [(p, y) for p, y in pairs if a <= p < z]
        if sel:
            out.append({"bin": f"{a:.2f}-{z:.2f}", "n": len(sel),
                        "predicted": round(sum(p for p, _ in sel) / len(sel), 3),
                        "observed": round(sum(y for _, y in sel) / len(sel), 3)})
    return out


def skill(pairs) -> float:
    """Brier skill vs a coin flip (0.25). <0 means worse than guessing."""
    b = brier(pairs)
    return 1 - b / 0.25 if pairs else 0.0


@dataclass
class Isotonic:
    xs: list[float]
    ys: list[float]

    @classmethod
    def fit(cls, pairs: list[tuple[float, int]], prior_strength: int = 20, min_block: int = 12,
            ceiling: float = 0.80):
        """PAV on blocks of >= min_block points, shrunk toward 0.5, anchored at (0.5, 0.5),
        clipped to `ceiling`: thin buckets cannot shout and no verdict claims certainty."""
        if not pairs:
            return cls([0.5, 1.0], [0.5, 0.5])
        pts = sorted(pairs, key=lambda t: t[0])          # sort on p only; ties stay together below
        blocks, cur = [], [0.0, 0, 0]
        for i, (p, y) in enumerate(pts):
            cur[0] += p; cur[1] += y; cur[2] += 1
            nxt = pts[i + 1][0] if i + 1 < len(pts) else None
            if cur[2] >= min_block and nxt != p:
                blocks.append(cur); cur = [0.0, 0, 0]
        if cur[2]:
            blocks.append(cur)
        if len(blocks) > 1 and blocks[-1][2] < min_block:
            b = blocks.pop(); blocks[-1] = [blocks[-1][0] + b[0], blocks[-1][1] + b[1], blocks[-1][2] + b[2]]
        i = 0
        while i < len(blocks) - 1:
            if blocks[i][1] / blocks[i][2] > blocks[i + 1][1] / blocks[i + 1][2]:
                a, b = blocks[i], blocks.pop(i + 1)
                a[0] += b[0]; a[1] += b[1]; a[2] += b[2]
                i = max(i - 1, 0)
            else:
                i += 1
        xs = [b[0] / b[2] for b in blocks]
        ys = [b[1] / b[2] for b in blocks]
        n = len(pairs)
        k = n / (n + prior_strength)
        ys = [min(ceiling, max(0.5, 0.5 + k * (y - 0.5))) for y in ys]
        for i in range(1, len(ys)):           # keep monotone after clipping
            ys[i] = max(ys[i], ys[i - 1])
        if xs[0] > 0.5:
            xs, ys = [0.5] + xs, [0.5] + ys
        return cls(xs, ys)

    def __call__(self, p: float) -> float:
        xs, ys = self.xs, self.ys
        if p <= xs[0]:
            return ys[0]
        if p >= xs[-1]:   # beyond the evidence: extend gently, never past the ceiling
            return min(0.80, ys[-1] + 0.25 * (p - xs[-1]))
        for i in range(1, len(xs)):
            if p <= xs[i]:
                t = (p - xs[i - 1]) / (xs[i] - xs[i - 1] or 1)
                return ys[i - 1] + t * (ys[i] - ys[i - 1])
        return ys[-1]

    def as_dict(self):
        return {"xs": [round(x, 4) for x in self.xs], "ys": [round(y, 4) for y in self.ys]}

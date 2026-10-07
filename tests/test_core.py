"""Offline tests: signing, calibration, council logic, sizing. Run: python -m pytest -q"""
import base64, hashlib, hmac
from modulus.clients.binance_web3 import sign
from modulus.calibration import Isotonic, brier, ece
from modulus.council import Council
from modulus.elders.base import Elder, Opinion
from modulus.sizing import size_usd
from modulus.config import RiskLimits
from modulus.universe import Asset, Leg


def test_signature_matches_reference_hmac():
    ts, path = "2026-10-07T08:00:00.000Z", "/build/api/v1/dex/market/rwa/platforms?platformId=bstock"
    want = base64.b64encode(hmac.new(b"s3cret", f"{ts}GET{path}".encode(), hashlib.sha256).digest()).decode()
    assert sign("s3cret", ts, "get", path) == want


def test_isotonic_is_monotone_shrunk_and_capped():
    pairs = [(0.55, 0)] * 30 + [(0.6, 1)] * 20 + [(0.6, 0)] * 10 + [(0.7, 1)] * 40
    c = Isotonic.fit(pairs)
    vals = [c(x) for x in (0.5, 0.55, 0.6, 0.65, 0.7, 0.95)]
    assert vals == sorted(vals)
    assert max(vals) <= 0.80 and c(0.5) == 0.5


def test_tied_probabilities_do_not_fake_confidence():
    pairs = [(0.6, 0)] * 40 + [(0.6, 1)] * 60      # 60% hit rate at one raw value
    assert abs(Isotonic.fit(pairs)(0.6) - (0.5 + 100 / 120 * 0.1)) < 1e-6


def test_scores():
    assert brier([(1.0, 1), (0.0, 0)]) == 0
    assert abs(ece([(0.7, 1), (0.7, 0)]) - 0.2) < 1e-9


class Fixed(Elder):
    def __init__(self, name, d, p, w=1.0, veto=False):
        self.name, self.d, self.p, self.prior_weight, self.v = name, d, p, w, veto

    def opine(self, asset, ctx):
        return Opinion(self.name, self.d, self.p, f"{self.name} says {self.d}", veto=self.v)


def asset():
    a = Asset("NVDA", 1)
    a.legs["bstock"] = Leg("bstock", "NVDAB", "0x02fca66c1d1afb4e2a7884261eb00f63598a7436", 1.0)
    return a


IDENT = Isotonic([0.5, 1.0], [0.5, 1.0])


def test_sentinel_veto_wins():
    c = Council([Fixed("gap", 1, 0.9), Fixed("whale", 1, 0.9), Fixed("sentinel", 0, 0.5, 0, veto=True)], IDENT)
    assert c.deliberate(asset(), {}).action == "VETO"


def test_quorum_blocks_single_elder():
    c = Council([Fixed("gap", 1, 0.9)], IDENT)
    v = c.deliberate(asset(), {})
    assert v.action == "HOLD" and "quorum" in v.headline


def test_dissent_lowers_confidence():
    agree = Council([Fixed("a", 1, 0.7), Fixed("b", 1, 0.7), Fixed("c", 1, 0.7)], IDENT).deliberate(asset(), {})
    split = Council([Fixed("a", 1, 0.7), Fixed("b", 1, 0.7), Fixed("c", -1, 0.7)], IDENT).deliberate(asset(), {})
    assert split.confidence < agree.confidence and split.dissent > 0


def test_sizing_respects_caps_and_confidence():
    lim = RiskLimits(max_trade_usd=5, max_daily_usd=20)
    assert size_usd(0.50, 0, 100, 0, 0, lim) == 0
    assert size_usd(0.62, 0, 100, 0, 0, lim) == 5.0
    assert size_usd(0.62, 0, 100, 19.5, 0, lim) == 0

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


def test_two_nights_clock():
    from datetime import datetime, timezone
    from modulus.clock import regime
    assert regime(datetime(2026, 10, 10, 12, tzinfo=timezone.utc)) == "dark_weekend"   # Saturday
    assert regime(datetime(2026, 10, 11, 23, tzinfo=timezone.utc)) == "dawn"           # Sunday after CME reopen
    assert regime(datetime(2026, 10, 7, 15, tzinfo=timezone.utc)) == "regular"
    assert regime(datetime(2026, 10, 7, 2, tzinfo=timezone.utc)) == "weeknight"


def test_night_watchman_fades_weekend_and_follows_weeknight():
    from datetime import datetime, timezone
    from modulus.elders.gap import GapElder, last_us_close_ms
    a = Asset("XYZ", 1); a.legs["bstock"] = Leg("bstock", "XYZB", "0x0", 1.0)
    sat = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    t0 = last_us_close_ms(sat)
    candles = [[t0, 0, 0, 0, "100"], [t0 + 3600_000 * 10, 0, 0, 0, "97"]]
    o = GapElder().opine(a, {"now": sat, "spot": {"XYZB": candles}, "market_drift": 0.0})
    assert o.direction == 1 and o.p > 0.6          # weekend dump -> buy the overshoot
    wed = datetime(2026, 10, 8, 3, tzinfo=timezone.utc)
    t1 = last_us_close_ms(wed)
    o2 = GapElder().opine(a, {"now": wed, "spot": {"XYZB": [[t1, 0, 0, 0, "100"], [t1 + 3600_000 * 6, 0, 0, 0, "97"]]}, "market_drift": 0.0})
    assert o2.direction == -1                      # weeknight dump is informed -> lean with it


def test_oracle_merkle_commit_is_provable():
    from modulus import oracle
    fc = {"NVDA": {"gap_hat_bps": 120.0, "p_up": 0.7}, "TSLA": {"gap_hat_bps": -80.0, "p_up": 0.38}, "MU": {"gap_hat_bps": 5.0, "p_up": 0.5}}
    root, levels = oracle.merkle([oracle.leaf("2026-10-09", t, fc[t]) for t in sorted(fc)])
    for i, t in enumerate(sorted(fc)):
        assert oracle.verify(oracle.leaf("2026-10-09", t, fc[t]), oracle.proof(levels, i), root)
    tampered = dict(fc["TSLA"], p_up=0.9)
    assert not oracle.verify(oracle.leaf("2026-10-09", "TSLA", tampered), oracle.proof(levels, 2), root)


def test_oracle_abstains_on_small_moves():
    from modulus import oracle
    model = {"b_mkt": 0.8, "b_idio": 0.5, "table": [(0.0, 0.5), (0.01, 0.7)]}
    assert oracle.p_up(0.002, model) == 0.5
    assert oracle.p_up(0.015, model) == 0.7
    assert abs(oracle.p_up(-0.015, model) - 0.3) < 1e-9

"""Tests that pin Modulus to the official Binance Web3 / Agentic Wallet / B402 docs (Oct 2026).
Offline: the network, the `baw` CLI and the B402 facilitator are all faked. Run: python -m pytest -q"""
import base64, hashlib, hmac, json, os, re, stat, sys, textwrap, urllib.request
import pytest

from modulus.clients import binance_web3 as bw
from modulus.config import Settings, RiskLimits, USDT_BSC
from modulus import executor as ex


def S(**kw):
    return Settings(api_key=kw.pop("api_key", "a"), api_secret=kw.pop("api_secret", "s"), **kw)


class FakeResp:
    def __init__(self, obj): self.b = json.dumps(obj).encode()
    def read(self, *a): return self.b
    def __enter__(self): return self
    def __exit__(self, *a): return False


def capture(monkeypatch, responses):
    """Patch urlopen; returns the list of captured requests. responses: list of dicts returned in order."""
    seen, it = [], iter(responses)
    def fake(req, timeout=0):
        seen.append(req)
        return FakeResp(next(it))
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setattr(bw.time, "sleep", lambda s: None)
    return seen


# ------------------------------------------------------------------ authentication
def test_prehash_matches_docs_recipe():
    ts, rp = "2026-05-11T10:08:00.000Z", "/build/api/v1/dex/market/price?chainId=1&symbol=ETH%20USDT"
    want = base64.b64encode(hmac.new(b"k", (ts + "GET" + rp).encode(), hashlib.sha256).digest()).decode()
    assert bw.sign("k", ts, "get", rp) == want


def test_iso_timestamp_format():
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", bw.iso_ms_now())


def test_signed_wire_path_has_build_prefix_and_raw_query(monkeypatch):
    seen = capture(monkeypatch, [{"code": 0, "data": []}])
    bw.BinanceWeb3(S()).rwa_platforms("bstock")
    r = seen[0]
    assert r.full_url == "https://web3.binance.com/build/api/v1/dex/market/rwa/platforms?platformId=bstock"
    h = {k.lower(): v for k, v in r.header_items()}
    assert h["x-oc-sign"] == bw.sign("s", h["x-oc-timestamp"], "GET", "/build/api/v1/dex/market/rwa/platforms?platformId=bstock")
    assert h["x-oc-apikey"] == "a" and "x-oc-nonce" in h and h["x-oc-recv-window"] == "10000"


def test_query_uses_percent20_not_plus():
    url, h, _ = bw.BinanceWeb3(S()).build_request("GET", "/x", {"q": "ETH USDT"})
    assert url.endswith("?q=ETH%20USDT")


def test_post_signs_exact_body_bytes():
    c = bw.BinanceWeb3(S())
    url, h, data = c.build_request("POST", "/api/v1/dex/market/price-info", body=[{"a": 1}], ts="2026-01-01T00:00:00.000Z")
    assert data == b'[{"a":1}]'
    assert h["X-OC-SIGN"] == bw.sign("s", "2026-01-01T00:00:00.000Z", "POST", "/build/api/v1/dex/market/price-info", '[{"a":1}]')


def test_business_error_in_http200_is_retried(monkeypatch):
    seen = capture(monkeypatch, [{"code": "50000", "msg": "busy"}, {"code": 0, "data": {"ok": 1}}])
    assert bw.BinanceWeb3(S()).gas_price() == {"ok": 1} and len(seen) == 2


def test_non_retryable_business_error_raises(monkeypatch):
    capture(monkeypatch, [{"code": "40369", "msg": "BSTOCK_INVALID_TRADING_TIME"}])
    with pytest.raises(bw.Web3ApiError) as e:
        bw.BinanceWeb3(S()).quote(USDT_BSC, "0xabc", "1000")
    assert str(e.value.code) == "40369"


# ------------------------------------------------------------------ request shapes per docs
def test_simulate_uses_evmTx(monkeypatch):
    seen = capture(monkeypatch, [{"code": 0, "data": {"status": "SUCCESS"}}])
    bw.BinanceWeb3(S()).simulate("0xF", "0xT", "0xdead", "0x10")
    body = json.loads(seen[0].data)
    assert body == {"binanceChainId": "56", "evmTx": {"from": "0xF", "to": "0xT", "value": "16", "data": "0xdead"}}


def test_b402_envelope_and_success_code(monkeypatch):
    seen = capture(monkeypatch, [{"code": "000000000", "data": {"kinds": [{"x": 1}]}}])
    assert bw.BinanceWeb3(S()).b402_supported() == {"kinds": [{"x": 1}]}
    assert json.loads(seen[0].data) == {"body": {}}
    assert seen[0].full_url.endswith("/build/api/v2/b402/supported")


def test_balances_portfolio_tracker_params(monkeypatch):
    seen = capture(monkeypatch, [{"code": 0, "data": 1}] * 3)
    c = bw.BinanceWeb3(S())
    c.balances("0xAbC")
    c.portfolio_overview("0xAbC")
    c.tracked_trades("1")
    assert "chains=56" in seen[0].full_url and "binanceChainId" not in seen[0].full_url
    assert "walletAddress=0xabc" in seen[1].full_url and "timeFrame=1" in seen[1].full_url
    assert "trackerType=1" in seen[2].full_url


def test_candles_lowercase_bar_and_layout(monkeypatch):
    seen = capture(monkeypatch, [{"code": 0, "data": [["1", "2", "0.5", "1.5", "100", "1700000000000", "9"]]}])
    rows = bw.BinanceWeb3(S()).candles("0xabc")
    assert "bar=1h" in seen[0].full_url
    assert bw.BinanceWeb3.candles_to_spot_layout(rows) == [[1700000000000, "1", "2", "0.5", "1.5", "100"]]


def test_price_info_batches_100(monkeypatch):
    seen = capture(monkeypatch, [{"code": 0, "data": [1]}] * 3)
    bw.BinanceWeb3(S()).price_info([f"0x{i}" for i in range(250)])
    assert [len(json.loads(r.data)) for r in seen] == [100, 100, 50]


def test_defi_investments_body(monkeypatch):
    seen = capture(monkeypatch, [{"code": 0, "data": []}])
    bw.BinanceWeb3(S()).defi_investments(USDT_BSC)
    b = json.loads(seen[0].data)
    assert b["investType"] == "Earn" and b["tokenAddressList"] == [USDT_BSC] and b["binanceChainId"] == "56"


# ------------------------------------------------------------------ executor helpers
def route(mode, out, fin="1000000000000000000", fd=18, td=18, **kw):
    return {"executionMode": mode, "toTokenAmount": out, "fromTokenAmount": fin, "quoteId": mode.lower(),
            "fromToken": {"decimal": fd}, "toToken": {"decimal": td}, **kw}


def test_pick_route_prefers_firm_rfq_within_10bps_else_best():
    swap, rfq = route("SWAP", "10000"), route("RFQ", "9995")
    assert ex.pick_route([swap, rfq])["executionMode"] == "RFQ"
    assert ex.pick_route([swap, route("RFQ", "9900")])["executionMode"] == "SWAP"
    with pytest.raises(bw.Web3ApiError):
        ex.pick_route([])


def test_amounts_round_down_with_token_decimals():
    assert ex.to_min_units("0.1234567", 6) == "123456"
    assert ex.to_min_units(5, 18) == "5000000000000000000"


def test_quote_price_and_adverse():
    r = route("RFQ", "25000000000000000", fin="5000000000000000000")      # $5 -> 0.025 token
    px = ex.quote_price(r, buy=True)
    assert abs(px - 200) < 1e-9
    assert abs(ex.adverse_pct(202, 200, True) - 1.0) < 1e-9 and ex.adverse_pct(198, 200, True) < 0


def test_sign_rfq_accepts_dict_json_and_0x1901():
    from eth_account import Account
    acct = Account.from_key("0x" + "11" * 32)
    td = {"types": {"EIP712Domain": [{"name": "name", "type": "string"}], "O": [{"name": "a", "type": "uint256"}]},
          "primaryType": "O", "domain": {"name": "x"}, "message": {"a": 1}}
    s1, s2 = ex.sign_rfq(acct, td), ex.sign_rfq(acct, json.dumps(td))
    assert s1 == s2 and s1.startswith("0x") and len(s1) == 132
    assert len(ex.sign_rfq(acct, "0x1901" + "ab" * 64)) == 132
    with pytest.raises(ValueError):
        ex.sign_rfq(acct, "garbage")


class V:
    def __init__(self, action="BUY", address="0x" + "b" * 40): self.action, self.address = action, address


def test_paper_fill_without_key():
    e = ex.Executor(Settings(api_key=None, api_secret=None))
    r = e.execute(V(), 5, 200.0, policy={"order_type": "limit", "max_slippage_pct": 0.5})
    assert r["status"] == "PAPER" and r["est_out"] == 0.025 and r["order_type"] == "limit"


def test_market_closed_40369_is_deferred_not_failed(monkeypatch):
    s = S(wallet_address="0x" + "1" * 40)
    e = ex.Executor(s)
    def boom(*a, **k): raise bw.Web3ApiError("40369", "BSTOCK_INVALID_TRADING_TIME", "quote")
    monkeypatch.setattr(e.api, "quote", boom)
    assert e.execute(V(), 5, 200.0)["status"] == "DEFERRED"


def test_dryrun_simulates_swap_route(monkeypatch):
    s = S(wallet_address="0x" + "1" * 40)
    e = ex.Executor(s)
    monkeypatch.setattr(e.api, "quote", lambda *a, **k: [route("SWAP", "25000000000000000", fin="5000000000000000000")])
    monkeypatch.setattr(e.api, "swap", lambda *a, **k: {"tx": {"from": "0x1", "to": "0x2", "data": "0xab", "value": "0"}})
    monkeypatch.setattr(e.api, "simulate", lambda *a, **k: {"status": "FAIL", "failReason": "insufficient allowance"})
    r = e.execute(V(), 5, 200.0)
    assert r["status"] == "SIM_FAILED" and r["reason"] == "insufficient allowance"


def test_dryrun_rejects_quote_far_from_reference(monkeypatch):
    e = ex.Executor(S(wallet_address="0x" + "1" * 40))
    monkeypatch.setattr(e.api, "quote", lambda *a, **k: [route("RFQ", "24000000000000000", fin="5000000000000000000")])
    assert e.execute(V(), 5, 200.0)["status"] == "REJECTED"           # $208.3 vs $200 ref = 4% worse


# ------------------------------------------------------------------ Agentic Wallet (fake `baw` binary)
FAKE_BAW = r'''#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
open(os.environ["BAW_LOG"], "a").write(json.dumps(a) + "\n")
def out(d): print(json.dumps({"success": True, "data": d})); sys.exit(0)
if a[:2] == ["wallet", "tx-lock"]: out({"status": "UNLOCKED"})
if a[:2] == ["wallet", "balance"]:
    tok = a[a.index("--tokenAddress") + 1]
    out([{"address": tok, "balance": "0.05" if tok.startswith("0xeee") else os.environ.get("HELD", "0")}])
if a[:2] == ["market-order", "quote"]: out({"fromCoinAmount": a[a.index("--fromTokenQty") + 1], "toCoinAmount": os.environ.get("TOQTY", "0.025"), "slippage": "0.005"})
if a[:2] == ["market-order", "swap"]: out({"orderId": "o1"})
if a[:2] == ["market-order", "list"]: out({"list": [{"orderId": "o1", "status": "FINISHED", "txHash": "0xhash"}]})
if a[0] == "limit-order" and a[1] in ("buy", "sell"): out({"strategyId": "s1"})
if a[:2] == ["limit-order", "list"]: out({"list": [{"strategyId": "s1", "status": "WORKING"}]})
if a[:2] == ["limit-order", "cancel"]: out({"status": "CANCELED"})
print(json.dumps({"success": False, "error": {"code": 1, "name": "UNKNOWN", "message": "unhandled " + " ".join(a)}})); sys.exit(1)
'''


_BAW_EXE_MAIN = (
    "import os, sys, runpy\n"
    'd = os.path.dirname(os.path.abspath(sys.argv[0]))\n'          # the .exe sits next to baw.py
    'sys.argv = [os.path.join(d, "baw.py")] + sys.argv[1:]\n'
    'runpy.run_path(sys.argv[0], run_name="__main__")\n'
)


def _baw_exe(dst):
    """Windows-only launcher. `modulus.clients.baw` shells out to a BARE `baw`
    (subprocess.run(["baw", ...]), no shell), and CreateProcess only auto-appends .exe - a .cmd/.bat
    raises FileNotFoundError (WinError 2), while shutil.which() still reports it available. So emit a
    real .exe: distlib's console-script launcher stub (pip bundles it) + shebang + a stored zip whose
    __main__.py execs the sibling baw.py, mirroring POSIX's shebang. Args reach the fake identically."""
    import pathlib, struct, io, zipfile
    stub = None
    for mod in ("pip._vendor.distlib", "distlib"):       # pip vendors distlib; plain distlib if present
        try:
            stub = pathlib.Path(__import__(mod, fromlist=["_"]).__file__).parent
            break
        except Exception:
            continue
    if stub is None:
        raise RuntimeError("fake_baw: no distlib launcher (pip._vendor.distlib) to build baw.exe on Windows")
    launcher = stub / ("t64.exe" if struct.calcsize("P") * 8 == 64 else "t32.exe")
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("__main__.py", _BAW_EXE_MAIN)
    dst.write_bytes(launcher.read_bytes() + b"#!" + sys.executable.encode("utf-8") + b"\n" + z.getvalue())


@pytest.fixture
def fake_baw(tmp_path, monkeypatch):
    (tmp_path / "baw.py").write_text(FAKE_BAW)          # the fake, runnable under either interpreter
    if os.name == "nt":
        _baw_exe(tmp_path / "baw.exe")                  # CreateProcess needs a real .exe, not a .cmd
    else:
        b = tmp_path / "baw"                            # extensionless + shebang, exactly as on POSIX
        b.write_text(FAKE_BAW)
        b.chmod(b.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "log"
    monkeypatch.setenv("BAW_LOG", str(log))
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(ex.pub, "asset_status", lambda addr: {"openState": True, "marketStatus": "overnight"})
    return lambda: [json.loads(l) for l in log.read_text().splitlines()]


def test_baw_weekend_policy_places_limit_order_not_market(fake_baw):
    e = ex.Executor(Settings(executor="baw"))
    r = e.execute(V(), 5, 200.0, policy={"order_type": "limit", "max_slippage_pct": 0.5})
    calls = fake_baw()
    assert r["mode"] == "baw-limit" and r["orderId"] == "s1" and r["triggerPrice"] == 199.5
    assert any(c[:2] == ["limit-order", "buy"] for c in calls)
    assert not any(c[:2] == ["market-order", "swap"] for c in calls)
    lb = next(c for c in calls if c[:2] == ["limit-order", "buy"])
    assert "--json" in lb and lb[lb.index("--binanceChainId") + 1] == "56" and lb[lb.index("--mev") + 1] == "true"
    assert ["wallet", "tx-lock", "--binanceChainId", "56", "--json"] in calls


def test_baw_weekday_policy_market_swap_polls_to_finished(fake_baw):
    r = ex.Executor(Settings(executor="baw")).execute(V(), 5, 200.0, policy={"order_type": "market", "max_slippage_pct": 1.0})
    assert r["status"] == "FINISHED" and r["txHash"] == "0xhash"


def test_baw_rejects_quote_worse_than_cap(fake_baw, monkeypatch):
    monkeypatch.setenv("TOQTY", "0.02")       # $250 per token vs $200 ref
    r = ex.Executor(Settings(executor="baw")).execute(V(), 5, 200.0, policy={"order_type": "market", "max_slippage_pct": 1.0})
    assert r["status"] == "REJECTED"


def test_baw_sell_uses_real_wallet_balance(fake_baw, monkeypatch):
    e = ex.Executor(Settings(executor="baw"))
    assert e.execute(V("SELL"), 5, 200.0)["status"] == "SKIPPED"        # holds nothing
    monkeypatch.setenv("HELD", "1.0")
    monkeypatch.setenv("TOQTY", "4.99")
    r = e.execute(V("SELL"), 5, 200.0, policy={"order_type": "market", "max_slippage_pct": 1.0})
    assert r["status"] == "FINISHED"
    q = next(c for c in fake_baw() if c[:2] == ["market-order", "quote"])
    assert float(q[q.index("--fromTokenQty") + 1]) == 0.025


def test_baw_closed_market_is_deferred(fake_baw, monkeypatch):
    monkeypatch.setattr(ex.pub, "asset_status", lambda a: {"openState": False, "marketStatus": "closed", "reasonCode": "MARKET_CLOSED"})
    assert ex.Executor(Settings(executor="baw")).execute(V(), 5, 200.0)["status"] == "DEFERRED"


def test_baw_missing_never_falls_back_to_paper(monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    r = ex.Executor(Settings(executor="baw")).execute(V(), 5, 200.0)
    assert r["status"] == "FAILED" and "not on PATH" in r["error"]


def test_reconcile_cancels_working_limits(fake_baw):
    out = ex.Executor(Settings(executor="baw")).reconcile_limits(cancel_working=True)
    assert out[0]["cancel"] == "CANCELED"


def test_x402_buyer_uses_paymentRequirements_flag(fake_baw):
    from modulus.clients.baw import Baw
    with pytest.raises(Exception):
        Baw().x402_preview({"x402Version": 2})
    c = fake_baw()[-1]
    assert c[:3] == ["x402-payment", "preview", "--paymentRequirements"] and "--url" not in c


# ------------------------------------------------------------------ Sentinel / Value per docs
def _asset(status=None, asset_type=1):
    from modulus.universe import Asset, Leg
    a = Asset("XYZ", asset_type)
    a.legs["bstock"] = Leg("bstock", "XYZB", "0x0", 1.0, {"statusInfo": status or {}})
    return a


def test_sentinel_vetoes_closed_and_paused():
    from modulus.elders.sentinel import SentinelElder
    s = SentinelElder()
    assert s.opine(_asset({"openState": False, "marketStatus": "closed", "reasonCode": "MARKET_CLOSED"}), {"audit": False}).veto
    assert s.opine(_asset({"openState": True, "marketStatus": "pause"}), {"audit": False}).veto
    assert not s.opine(_asset({"openState": True, "marketStatus": "overnight", "reasonCode": "TRADING"}), {"audit": False}).veto


def test_value_elder_abstains_on_pre_ipo():
    from modulus.elders.value import ValueElder
    assert ValueElder().opine(_asset(asset_type=2), {}).direction == 0


# ------------------------------------------------------------------ x402 V2 seller with a fake facilitator
PAYTO = "0x" + "9" * 40
U = "0xcE24439F2D9C6a2289F741120FE202248B666666"


@pytest.fixture
def x402(monkeypatch):
    monkeypatch.setenv("MODULUS_B402_PAYTO", PAYTO)
    import importlib
    import modulus.server.x402_api as m
    m = importlib.reload(m)
    kinds = [{"x402Version": 2, "scheme": "exact", "network": "eip155:56", "asset": U,
              "extra": {"assetTransferMethod": "eip3009", "name": "U", "version": "1"}}]
    calls = {"verify": 0, "settle": 0}
    monkeypatch.setattr(m.api, "b402_supported", lambda: {"kinds": kinds})
    def verify(inner):
        calls["verify"] += 1
        return {"isValid": True, "payer": "0xbuyer"}
    def settle(inner):
        calls["settle"] += 1
        return {"success": True, "transaction": "0xsettle", "network": "eip155:56", "payer": "0xbuyer"}
    monkeypatch.setattr(m.api, "b402_verify", verify)
    monkeypatch.setattr(m.api, "b402_settle", settle)
    monkeypatch.setattr(m, "_council", lambda t: {"symbol": t + "B", "action": "HOLD", "confidence": 0.6} if t != "ZZZZ" else None)
    from fastapi.testclient import TestClient
    return TestClient(m.app), m, calls


def test_x402_unpaid_returns_402_with_v2_header(x402):
    c, m, calls = x402
    r = c.get("/verdict/NVDA")
    assert r.status_code == 402
    pr = json.loads(base64.b64decode(r.headers["PAYMENT-REQUIRED"]))
    assert pr["x402Version"] == 2 and pr["accepts"][0]["payTo"] == PAYTO and pr["accepts"][0]["network"] == "eip155:56"
    assert pr["accepts"][0]["extra"]["assetTransferMethod"] == "eip3009" and "bazaar" in pr["extensions"]
    assert calls == {"verify": 0, "settle": 0}


def _pay(pr):
    return base64.b64encode(json.dumps({"x402Version": 2, "accepted": pr["accepts"][0], "payload": {"sig": "0x"}}).encode()).decode()


def test_x402_paid_returns_verdict_and_receipt(x402):
    c, m, calls = x402
    pr = json.loads(base64.b64decode(c.get("/verdict/NVDA").headers["PAYMENT-REQUIRED"]))
    r = c.get("/verdict/NVDA", headers={"PAYMENT-SIGNATURE": _pay(pr)})
    assert r.status_code == 200 and r.json()["symbol"] == "NVDAB"
    assert json.loads(base64.b64decode(r.headers["PAYMENT-RESPONSE"]))["transaction"] == "0xsettle"
    assert calls == {"verify": 1, "settle": 1}


def test_x402_tampered_amount_is_refused(x402):
    c, m, calls = x402
    pr = json.loads(base64.b64decode(c.get("/verdict/NVDA").headers["PAYMENT-REQUIRED"]))
    pr["accepts"][0]["amount"] = "1"
    assert c.get("/verdict/NVDA", headers={"PAYMENT-SIGNATURE": _pay(pr)}).status_code == 402
    assert calls["settle"] == 0


def test_x402_unknown_ticker_is_not_charged(x402):
    c, m, calls = x402
    pr = json.loads(base64.b64decode(c.get("/verdict/ZZZZ").headers["PAYMENT-REQUIRED"]))
    r = c.get("/verdict/ZZZZ", headers={"PAYMENT-SIGNATURE": _pay(pr)})
    assert r.status_code == 404 and calls["settle"] == 0


def test_core_endpoint_requires_token(monkeypatch):
    import importlib
    monkeypatch.setenv("MODULUS_CORE_TOKEN", "t0k")
    import modulus.server.x402_api as m
    m = importlib.reload(m)
    monkeypatch.setattr(m, "_council", lambda t: {"symbol": t})
    from fastapi.testclient import TestClient
    c = TestClient(m.core)
    assert c.get("/core/verdict/NVDA").status_code == 401
    assert c.get("/core/verdict/NVDA", headers={"authorization": "Bearer t0k"}).json() == {"symbol": "NVDA"}


# ------------------------------------------------------------------ MCP
def test_mcp_registers_all_seven_tools():
    import asyncio
    from modulus.server import mcp_server
    names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert names == {"modulus_verdict", "modulus_scan", "modulus_twins", "modulus_calibration",
                     "modulus_market_clock", "modulus_monday_oracle", "modulus_two_nights"}


# ------------------------------------------------------------------ ledger counts resting limits toward the daily cap
def test_daily_cap_counts_working_limit_orders(tmp_path):
    from modulus.ledger import Ledger
    L = Ledger(str(tmp_path / "x.sqlite"))
    L.record_order(1, "baw", "BUY", 5.0, "WORKING", "s1", {})
    L.record_order(2, "baw", "BUY", 5.0, "REJECTED", "", {})
    assert L.spent_today() == 5.0

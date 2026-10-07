"""Execution: check, simulate, trade small, verify. Rebuilt against the official docs (Oct 2026).

Modes
  dryrun : no key -> priced paper fill. With key -> Trading API /quote -> /swap build -> Transaction API
           /simulate (binanceChainId + evmTx{from,to,value,data}). No funds move.
  baw    : Binance Agentic Wallet. Status gate (openState / halts) -> tx-lock -> BNB gas floor ->
           quote vs reference price (quotes carry no priceImpact field) -> LIMIT order in thin hours
           (dark weekend / dawn) or MEV-protected market swap -> poll to a terminal state.
           bStocks are whitelisted and do NOT consume the wallet's dailyLimit, so Modulus' own
           RiskLimits ($5/trade, $20/day, resting limits included) are the binding guardrail.
  api    : direct Web3 API. bStock quotes can return a LiquidMesh SWAP route AND a PcsXRfq RFQ route.
           Pick the best net-out (prefer the firm RFQ price within rfq_prefer_bps). Allowance is read
           on-chain first; approval only when short, then RE-QUOTE (quoteId TTL 30 s, 40401).
           RFQ: sign rfq.typedDataToSign (dict | JSON string | 0x1901 blob) -> /order/submit (same
           requestId on retry) -> poll /order/{orderId} to FILLED|FAILED|EXPIRED|CANCELLED.
           SWAP: /swap (priceImpactProtectionPercent) -> /simulate -> sign -> /broadcast (MEV) -> poll.
"""
from __future__ import annotations
import json, time, uuid
from decimal import Decimal, ROUND_DOWN
from .config import SETTINGS, USDT_BSC, BNB_NATIVE
from .clients.binance_web3 import BinanceWeb3, Web3ApiError
from .clients.baw import Baw, BawError
from .clients import public_bapi as pub

HALT = {"ASSET_PAUSED", "MARKET_PAUSED", "MARKET_MAINTENANCE", "UNSUPPORTED", "ASSET_LIMITED"}
RFQ_TERMINAL = {"FILLED", "FAILED", "EXPIRED", "CANCELLED"}
DEFERRED_CODES = {"40369", "40367"}                       # BSTOCK_INVALID_TRADING_TIME: underlying market closed
NO_LIQ_CODES = {"40374", "40421", "40441"}
KYT_CODES = {"40311", "40312", "40313", "40314", "40434"}
ERC20_ALLOWANCE_ABI = [{"name": "allowance", "type": "function", "stateMutability": "view",
                        "inputs": [{"name": "o", "type": "address"}, {"name": "s", "type": "address"}],
                        "outputs": [{"type": "uint256"}]}]


def to_min_units(qty, decimals: int) -> str:
    """Human qty -> smallest unit, rounded DOWN (never exceed a balance)."""
    return str(int((Decimal(str(qty)) * (Decimal(10) ** int(decimals))).to_integral_value(ROUND_DOWN)))


def pick_route(quote, prefer_bps: float = 10.0) -> dict:
    routes = quote if isinstance(quote, list) else [quote]
    routes = [r for r in routes if r and r.get("toTokenAmount")]
    if not routes:
        raise Web3ApiError("NO_ROUTE", "quote returned no routes", "quote")
    best = max(routes, key=lambda r: int(r["toTokenAmount"]))
    rfq = [r for r in routes if r.get("executionMode") == "RFQ"]
    if rfq and int(rfq[0]["toTokenAmount"]) * 10_000 >= int(best["toTokenAmount"]) * (10_000 - prefer_bps):
        return rfq[0]
    return best


def quote_price(route: dict, buy: bool) -> float | None:
    """USD per token implied by a route (stablecoin leg ~ $1)."""
    try:
        di, do = int(route["fromToken"]["decimal"]), int(route["toToken"]["decimal"])
        fi, to = int(route["fromTokenAmount"]) / 10 ** di, int(route["toTokenAmount"]) / 10 ** do
    except (KeyError, TypeError, ValueError):
        return None
    if fi <= 0 or to <= 0:
        return None
    return fi / to if buy else to / fi


def adverse_pct(px: float, ref: float, buy: bool) -> float:
    """How much worse than the reference price we would trade, in % (positive = worse)."""
    return ((px / ref - 1) if buy else (ref / px - 1)) * 100


def sign_rfq(acct, tdata) -> str:
    from eth_account.messages import encode_typed_data
    from eth_utils import keccak
    if isinstance(tdata, str) and tdata.strip().startswith("{"):
        tdata = json.loads(tdata)
    if isinstance(tdata, dict):
        sig = acct.sign_message(encode_typed_data(full_message=tdata)).signature
    elif isinstance(tdata, str) and tdata.startswith("0x1901"):
        sig = acct.unsafe_sign_hash(keccak(hexstr=tdata)).signature
    else:
        raise ValueError("unknown typedDataToSign format")
    h = sig.hex()
    return h if h.startswith("0x") else "0x" + h


class Executor:
    def __init__(self, settings=SETTINGS):
        self.s = settings
        self.api = BinanceWeb3(settings)
        self.baw = Baw()
        self._w3 = None

    @property
    def w3(self):
        if self._w3 is None:
            from web3 import Web3
            self._w3 = Web3(Web3.HTTPProvider(self.s.rpc_url))
        return self._w3

    # ------------------------------------------------------------------ entry point
    def execute(self, verdict, usd: float, ref_price: float, token_qty_held: float | None = None,
                policy: dict | None = None, decimals: dict | None = None) -> dict:
        policy = policy or {"order_type": "market", "max_slippage_pct": self.s.risk.max_slippage_pct}
        if usd <= 0:
            return {"status": "SKIPPED", "reason": "size below $1"}
        buy = verdict.action == "BUY"
        frm, to = (USDT_BSC, verdict.address) if buy else (verdict.address, USDT_BSC)
        mode = self.s.executor
        try:
            if mode == "baw":
                if not self.baw.available:                  # never silently paper-trade a live run
                    return {"status": "FAILED", "error": "MODULUS_EXECUTOR=baw but `baw` is not on PATH"}
                held = 0.0 if buy else self.baw.token_qty(verdict.address)
                qty = usd if buy else min(held, usd / ref_price)
                if not buy and qty <= 0:
                    return {"status": "SKIPPED", "reason": "nothing held to sell (baw wallet balance)"}
                return self._baw(frm, to, qty, buy, ref_price, policy, verdict.address)
            qty = usd if buy else min(token_qty_held or 0.0, usd / ref_price)
            if not buy and qty <= 0:
                return {"status": "SKIPPED", "reason": "nothing held to sell"}
            dec = int((decimals or {}).get(frm.lower(), 18))
            if mode == "api" and self.s.has_api_key and self.s.private_key:
                return self._api_live(frm, to, to_min_units(qty, dec), buy, ref_price, policy)
            return self._dryrun(frm, to, qty, to_min_units(qty, dec), buy, ref_price, policy)
        except Web3ApiError as e:
            c = str(e.code)
            if c in DEFERRED_CODES:
                return {"status": "DEFERRED", "reason": "underlying market closed (40369)", "error": str(e)}
            if c in NO_LIQ_CODES:
                return {"status": "SKIPPED", "reason": "no RWA liquidity", "error": str(e)}
            if c in KYT_CODES:
                return {"status": "BLOCKED_KYT", "error": str(e)}
            return {"status": "FAILED", "error": str(e), "code": e.code}
        except BawError as e:
            return {"status": "FAILED", "error": str(e), "code": e.code, "name": e.name}   # relayed verbatim

    # ------------------------------------------------------------------ dry run
    def _dryrun(self, frm, to, qty, amt, buy, ref_price, policy):
        if not self.s.has_api_key or not self.s.wallet_address:
            fill = qty / ref_price if buy else qty * ref_price
            return {"status": "PAPER", "mode": "paper", "est_out": round(fill, 6), "order_type": policy.get("order_type"),
                    "note": "no API key: priced from the reference price"}
        route = pick_route(self.api.quote(frm, to, amt, self.s.wallet_address), self.s.risk.rfq_prefer_bps)
        px = quote_price(route, buy)
        out = {"status": "SIMULATED", "mode": "dryrun", "executionMode": route.get("executionMode"),
               "vendor": route.get("vendorName"), "quoteId": route.get("quoteId"), "toAmount": route.get("toTokenAmount"),
               "quote_px": px, "order_type": policy.get("order_type")}
        if px and ref_price and adverse_pct(px, ref_price, buy) > float(policy.get("max_slippage_pct", 1.0)):
            out.update(status="REJECTED", reason=f"quote {px:.4f} vs ref {ref_price:.4f}")
            return out
        if route.get("executionMode") == "RFQ":
            out["note"] = "RFQ route: firm price, nothing on-chain to simulate before signing"
            return out
        sw = self.api.swap(route["quoteId"], frm, to, amt, self.s.wallet_address, policy.get("max_slippage_pct", 1.0),
                           price_impact_pct=policy.get("max_slippage_pct", 1.0))
        tx = sw["tx"]
        sim = self.api.simulate(tx["from"], tx["to"], tx["data"], tx.get("value", "0")) or {}
        out["simulation"] = sim
        if str(sim.get("status", "")).upper() != "SUCCESS":
            out.update(status="SIM_FAILED", reason=sim.get("failReason"))
        return out

    # ------------------------------------------------------------------ agentic wallet
    def _baw(self, frm, to, qty, buy, ref_price, policy, token_addr):
        cap = float(policy.get("max_slippage_pct", self.s.risk.max_slippage_pct))
        st = pub.asset_status(token_addr) or {}
        if st.get("reasonCode") in HALT or st.get("openState") is False:
            return {"status": "DEFERRED", "reason": f"asset not tradable now: {st.get('marketStatus')}/{st.get('reasonCode')}"}
        if self.baw.is_locked():
            return {"status": "SKIPPED", "reason": "wallet tx-lock LOCKED (pending tx or App double-confirm)"}
        if self.baw.token_qty(BNB_NATIVE) < self.s.risk.min_gas_bnb:
            return {"status": "SKIPPED", "reason": "BNB gas balance below floor"}
        q = self.baw.quote(qty, frm, to, slippage=cap)
        px = Baw.quote_price(q, buy)
        if not px or not ref_price:
            return {"status": "REJECTED", "reason": "unparseable quote", "quote": q}
        bad = adverse_pct(px, ref_price, buy)
        if bad > cap:
            return {"status": "REJECTED", "reason": f"quote {px:.4f} is {bad:.2f}% worse than ref {ref_price:.4f} (cap {cap}%)"}
        if policy.get("order_type") == "limit":        # thin hours: rest a limit, never fall back to market
            off = self.s.risk.limit_offset_pct / 100
            trig = float(f"{(ref_price * (1 - off) if buy else ref_price * (1 + off)):.6g}")
            r = (self.baw.limit_buy if buy else self.baw.limit_sell)(trig, qty, frm, to, slippage=cap, mev=True)
            sid = (r.get("data") or {}).get("strategyId")
            lo = self.baw.limit_order(sid) if sid else {}
            return {"status": lo.get("status") or "WORKING", "mode": "baw-limit", "orderId": sid,
                    "triggerPrice": trig, "quote_px": px, "detail": lo}
        r = self.baw.swap(qty, frm, to, slippage=cap, mev=True)
        oid = (r.get("data") or {}).get("orderId")
        final = self.baw.wait_market_order(oid) if oid else {"status": "UNKNOWN"}
        return {"status": final.get("status"), "mode": "baw", "orderId": oid, "txHash": final.get("txHash"),
                "quote_px": px, "detail": final}

    def reconcile_limits(self, cancel_working: bool = False) -> list[dict]:
        """At dawn/regular, cancel weekend fade orders still WORKING so they cannot fill on Monday's informed tape."""
        out = []
        for o in self.baw.limit_orders():
            row = {k: o.get(k) for k in ("strategyId", "status", "side", "triggerPrice", "txHash")}
            if cancel_working and o.get("status") == "WORKING":
                try:
                    row["cancel"] = (self.baw.limit_cancel(o["strategyId"]).get("data") or {}).get("status")
                except BawError as e:
                    row["cancel_error"] = str(e)
            out.append(row)
        return out

    # ------------------------------------------------------------------ direct API
    def _quote(self, frm, to, amt, wallet):
        return pick_route(self.api.quote(frm, to, amt, wallet), self.s.risk.rfq_prefer_bps)

    def _api_live(self, frm, to, amt, buy, ref_price, policy):
        from eth_account import Account
        acct = Account.from_key(self.s.private_key)
        cap = float(policy.get("max_slippage_pct", self.s.risk.max_slippage_pct))
        route = self._quote(frm, to, amt, acct.address)
        if self._ensure_allowance(frm, amt, route.get("vendorName") if route.get("executionMode") == "RFQ" else None,
                                  acct, route.get("approveTarget")):
            route = self._quote(frm, to, amt, acct.address)          # quoteId TTL 30 s: re-quote after approving
        px = quote_price(route, buy)
        if px and ref_price and adverse_pct(px, ref_price, buy) > cap:
            return {"status": "REJECTED", "reason": f"quote {px:.4f} vs ref {ref_price:.4f} > {cap}%"}
        try:
            sw = self.api.swap(route["quoteId"], frm, to, amt, acct.address, cap, price_impact_pct=cap)
        except Web3ApiError as e:
            if str(e.code) != "40401":
                raise
            route = self._quote(frm, to, amt, acct.address)
            sw = self.api.swap(route["quoteId"], frm, to, amt, acct.address, cap, price_impact_pct=cap)
        if route.get("executionMode") == "RFQ" or sw.get("rfq"):
            return self._rfq(route, sw["rfq"], acct)
        return self._swap_live(sw["tx"], acct)

    def _rfq(self, route, rfq, acct):
        qid = rfq.get("orderId") or route["quoteId"]
        req_id = str(uuid.uuid4())
        sub = None
        for _ in range(3):
            try:
                sub = self.api.rfq_submit(sign_rfq(acct, rfq["typedDataToSign"]), rfq.get("vendor") or route.get("vendorName"),
                                          qid, req_id, signing_scheme=rfq.get("signingScheme"))
                break
            except Web3ApiError as e:
                if str(e.code) != "42901":
                    raise
                time.sleep(2)                                         # same requestId on retry
        oid = (sub or {}).get("orderId")
        if not oid:
            return {"status": "FAILED", "mode": "api-rfq", "error": "order/submit returned no orderId", "detail": sub}
        for i in range(40):
            st = self.api.rfq_status(oid) or {}
            if st.get("status") in RFQ_TERMINAL:
                return {"status": st["status"], "mode": "api-rfq", "orderId": oid, "txHash": st.get("txHash"),
                        "fromAmount": st.get("fromAmount"), "toAmount": st.get("toAmount"), "detail": st}
            time.sleep(min(2 + i * 0.5, 6))
        return {"status": "PENDING", "mode": "api-rfq", "orderId": oid}

    def _swap_live(self, tx, acct):
        from web3 import Web3
        if tx["from"].lower() != acct.address.lower():
            raise Web3ApiError("SENDER_MISMATCH", tx["from"], "swap")
        sim = self.api.simulate(tx["from"], tx["to"], tx["data"], tx.get("value", "0")) or {}
        if str(sim.get("status", "")).upper() != "SUCCESS":
            return {"status": "REJECTED", "reason": f"simulation: {sim.get('failReason')}"}
        t = {"chainId": 56, "nonce": self.w3.eth.get_transaction_count(acct.address, "pending"),
             "to": Web3.to_checksum_address(tx["to"]), "data": tx["data"],
             "value": int(str(tx.get("value", "0")), 0), "gas": int(tx["gas"])}
        if tx.get("maxPriorityFeePerGas"):
            t["maxFeePerGas"], t["maxPriorityFeePerGas"] = int(tx["gasPrice"]), int(tx["maxPriorityFeePerGas"])
        else:
            t["gasPrice"] = int(tx["gasPrice"])
        raw = acct.sign_transaction(t).raw_transaction.hex()
        b = self.api.broadcast("0x" + raw.removeprefix("0x"), acct.address, mev=True)
        return {"status": self._wait_tx(b["txHash"]), "mode": "api-swap", "orderId": b.get("orderId"),
                "txHash": b["txHash"], "minReceive": tx.get("minReceiveAmount")}

    def _wait_tx(self, h, tries=40) -> str:
        for _ in range(tries):
            d = self.api.tx_detail(h) or []
            if d and d[0].get("txStatus") in ("success", "fail"):
                return "FILLED" if d[0]["txStatus"] == "success" else "FAILED"
            time.sleep(3)
        return "PENDING"

    def _ensure_allowance(self, token, amt, vendor, acct, spender_hint=None) -> bool:
        """True only if an approval tx was sent (caller must re-quote)."""
        from web3 import Web3
        if token.lower() == BNB_NATIVE:
            return False
        ap = self.api.approve_tx(token, amt, vendor) or []
        if not ap:
            return False
        item = ap[0]
        spender = item.get("dexContractAddress") or spender_hint
        if spender:
            erc20 = self.w3.eth.contract(Web3.to_checksum_address(token), abi=ERC20_ALLOWANCE_ABI)
            if erc20.functions.allowance(acct.address, Web3.to_checksum_address(spender)).call() >= int(amt):
                return False
        tx = {"chainId": 56, "nonce": self.w3.eth.get_transaction_count(acct.address, "pending"),
              "to": Web3.to_checksum_address(token), "data": item["data"], "value": 0,
              "gas": int(item["gasLimit"]), "gasPrice": int(item["gasPrice"])}
        raw = acct.sign_transaction(tx).raw_transaction.hex()
        h = self.api.broadcast("0x" + raw.removeprefix("0x"), acct.address)["txHash"]
        if self._wait_tx(h) != "FILLED":
            raise Web3ApiError("APPROVE_FAIL", h, "approve")
        return True

"""Execution: simulate first, then trade small, then verify.

Modes
  dryrun : Trading API quote -> swap build -> Transaction API simulate. No funds move.
           (Falls back to a priced paper fill from public data when no API key is set.)
  baw    : Binance Agentic Wallet. quote -> slippage check -> market-order swap (MEV protected)
           -> poll market-order list to FINISHED/FAILED. Agentic Wallet's own daily quota is the
           outer guardrail; Modulus' RiskLimits are the inner one.
  api    : direct Web3 API. RFQ flow for equity tokens: /quote (executionMode=RFQ, vendorName)
           -> /approve-transaction(vendor) -> /swap -> sign rfq.typedDataToSign (EIP-712)
           -> /order/submit -> poll /order/{id}. Regular SWAP flow otherwise, broadcast with
           enableMevProtection=true, then Wallet API tx-detail until success/fail.
"""
from __future__ import annotations
import time, uuid
from .config import SETTINGS, USDT_BSC
from .clients.binance_web3 import BinanceWeb3, Web3ApiError
from .clients.baw import Baw, BawError


class Executor:
    def __init__(self, settings=SETTINGS):
        self.s = settings
        self.api = BinanceWeb3(settings)
        self.baw = Baw()

    def execute(self, verdict, usd: float, ref_price: float, token_qty_held: float = 0.0) -> dict:
        if usd <= 0:
            return {"status": "SKIPPED", "reason": "size below $1"}
        buy = verdict.action == "BUY"
        frm, to = (USDT_BSC, verdict.address) if buy else (verdict.address, USDT_BSC)
        qty = usd if buy else min(token_qty_held, usd / ref_price)
        if not buy and qty <= 0:
            return {"status": "SKIPPED", "reason": "nothing held to sell"}
        mode = self.s.executor
        try:
            if mode == "baw" and self.baw.available:
                return self._baw(frm, to, qty)
            if mode == "api" and self.s.has_api_key and self.s.private_key:
                return self._api_live(frm, to, qty, buy, ref_price)
            return self._dryrun(frm, to, qty, buy, ref_price)
        except (BawError, Web3ApiError) as e:
            return {"status": "FAILED", "error": str(e)}   # relayed verbatim

    # ------------------------------------------------------------------ dry run
    def _dryrun(self, frm, to, qty, buy, ref_price):
        if not self.s.has_api_key or not self.s.wallet_address:
            fill = qty / ref_price if buy else qty * ref_price
            return {"status": "PAPER", "mode": "paper", "est_out": round(fill, 6), "note": "no API key: priced from on-chain reference"}
        wei = int(qty * 10 ** 18)
        q = self.api.quote(frm, to, wei, self.s.wallet_address)
        route = q[0] if isinstance(q, list) else q
        out = {"status": "SIMULATED", "mode": "dryrun", "executionMode": route.get("executionMode"),
               "vendor": route.get("vendorName"), "quoteId": route.get("quoteId"), "toAmount": route.get("toTokenAmount")}
        if route.get("executionMode") == "RFQ":
            out["note"] = "RFQ route: simulation is the signed EIP-712 order check, no raw tx to simulate"
            return out
        sw = self.api.swap(route["quoteId"], frm, to, wei, self.s.wallet_address, self.s.risk.max_slippage_pct)
        tx = sw["tx"]
        out["simulation"] = self.api.simulate({"fromAddress": tx["from"], "toAddress": tx["to"],
                                                "txAmount": tx.get("value", "0"), "extJson": {"inputData": tx["data"]}})
        return out

    # ------------------------------------------------------------------ agentic wallet
    def _baw(self, frm, to, qty):
        q = self.baw.quote(qty, frm, to)
        impact = abs(float((q.get("data") or {}).get("priceImpact", 0) or 0))
        if impact > self.s.risk.max_slippage_pct:
            return {"status": "REJECTED", "reason": f"price impact {impact}% > cap", "quote": q}
        r = self.baw.swap(qty, frm, to, slippage=self.s.risk.max_slippage_pct, mev=True)
        oid = (r.get("data") or {}).get("orderId")
        final = self.baw.wait_market_order(oid) if oid else {"status": "UNKNOWN"}
        return {"status": final.get("status"), "mode": "baw", "orderId": oid, "detail": final}

    # ------------------------------------------------------------------ direct API (RFQ aware)
    def _api_live(self, frm, to, qty, buy, ref_price):
        from eth_account import Account
        from eth_account.messages import encode_typed_data
        acct = Account.from_key(self.s.private_key)
        wei = int(qty * 10 ** 18)
        route = (lambda q: q[0] if isinstance(q, list) else q)(self.api.quote(frm, to, wei, acct.address))
        if route.get("executionMode") == "RFQ":
            vendor = route.get("vendorName")
            self._ensure_allowance(frm, wei, vendor, acct)
            sw = self.api.swap(route["quoteId"], frm, to, wei, acct.address, self.s.risk.max_slippage_pct)
            rfq = sw["rfq"]
            sig = Account.sign_message(encode_typed_data(full_message=rfq["typedDataToSign"]), acct.key).signature.hex()
            sub = self.api.rfq_submit("0x" + sig.removeprefix("0x"), rfq["vendor"], rfq["orderId"], str(uuid.uuid4()))
            oid = sub.get("orderId") or rfq["orderId"]
            for _ in range(30):
                st = self.api.rfq_status(oid)
                if st.get("status") in ("FILLED", "FAILED"):
                    return {"status": st["status"], "mode": "api-rfq", "orderId": oid, "detail": st}
                time.sleep(3)
            return {"status": "PENDING", "mode": "api-rfq", "orderId": oid}
        raise Web3ApiError("SWAP_MODE", "non-RFQ live path: use baw executor for raw swaps", "executor")

    def _ensure_allowance(self, token, wei, vendor, acct):
        if token.lower() == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee":
            return
        ap = self.api.approve_tx(token, wei, vendor)
        if not ap:
            return
        # sign + broadcast approval, then wait for confirmation (see Trading API integration flow, step 1)
        from web3 import Web3
        import os
        w3 = Web3(Web3.HTTPProvider(os.getenv("EVM_RPC_URL", "https://bsc-dataseed.bnbchain.org")))
        item = ap[0]
        tx = {"chainId": 56, "nonce": w3.eth.get_transaction_count(acct.address, "pending"), "to": Web3.to_checksum_address(token),
              "data": item["data"], "value": 0, "gas": int(item["gasLimit"]), "gasPrice": int(item["gasPrice"])}
        raw = acct.sign_transaction(tx).raw_transaction.hex()
        h = self.api.broadcast("0x" + raw.removeprefix("0x"), acct.address)["txHash"]
        for _ in range(40):
            d = self.api.tx_detail(h)
            if d and d[0].get("txStatus") in ("success", "fail"):
                if d[0]["txStatus"] == "fail":
                    raise Web3ApiError("APPROVE_FAIL", h, "approve")
                return
            time.sleep(3)

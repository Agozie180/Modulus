"""Binance Agentic Wallet (`baw` CLI) adapter - the AI execution layer.

Install:  npx skills add binance/binance-skills-hub/skills/binance-web3/binance-agentic-wallet
          npm i -g @binance/agentic-wallet   (provides `baw`)
Skills Modulus drives: binance-agentic-wallet (market-order, limit-order, wallet,
x402-payment), binance-wallet-tracker (whale groups + smart-money flow),
binance-leaderboard (wallet archetype scoring), binance-trading-signal
(smart-money signal feed), query-token-audit (pre-trade security check),
binance-tokenized-securities-info (ticker -> contract + status).

Every call appends --json and is parsed. Errors are relayed verbatim (skill rule).
"""
from __future__ import annotations
import json, shutil, subprocess, time
from ..config import BSC


class BawError(RuntimeError):
    pass


class Baw:
    def __init__(self, binary: str = "baw", timeout: int = 90):
        self.bin, self.timeout = binary, timeout

    @property
    def available(self) -> bool:
        return shutil.which(self.bin) is not None

    def run(self, *args: str) -> dict:
        cmd = [self.bin, *args, "--json"]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
        out = (p.stdout or "").strip()
        try:
            data = json.loads(out) if out else {}
        except json.JSONDecodeError:
            raise BawError(out or p.stderr)
        if p.returncode != 0 or (isinstance(data, dict) and data.get("success") is False):
            raise BawError(json.dumps(data)[:500] or p.stderr)  # verbatim, no reinterpretation
        return data

    # ---------------------------------------------------------- wallet
    def status(self):          return self.run("wallet", "status")
    def address(self):         return self.run("wallet", "address")
    def balance(self):         return self.run("wallet", "balance")
    def settings(self):        return self.run("wallet", "settings")   # daily quota = hard outer guardrail
    def tx_lock(self):         return self.run("wallet", "tx-lock")

    # ---------------------------------------------------------- trading
    def quote(self, qty, from_token, to_token, slippage="auto", chain=BSC):
        return self.run("market-order", "quote", "--fromTokenQty", str(qty), "--fromToken", from_token,
                        "--toToken", to_token, "--binanceChainId", chain, "--slippage", str(slippage))

    def swap(self, qty, from_token, to_token, slippage="auto", mev=True, chain=BSC):
        return self.run("market-order", "swap", "--fromTokenQty", str(qty), "--fromToken", from_token,
                        "--toToken", to_token, "--binanceChainId", chain, "--slippage", str(slippage),
                        "--mev", "true" if mev else "false")

    def wait_market_order(self, order_id, timeout_s=120):
        """Skill rule: an orderId is NOT a completed swap. Poll to FINISHED/FAILED."""
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            r = self.run("market-order", "list", "--orderId", str(order_id))
            items = (r.get("data") or {}).get("list") or r.get("data") or []
            st = (items[0] if isinstance(items, list) and items else {}).get("status")
            if st in ("FINISHED", "FAILED"):
                return items[0]
            time.sleep(4)
        return {"status": "TIMEOUT", "orderId": order_id}

    def limit_buy(self, trigger, qty, from_token, to_token, chain=BSC):
        return self.run("limit-order", "buy", "--triggerPrice", str(trigger), "--fromTokenQty", str(qty),
                        "--fromToken", from_token, "--toToken", to_token, "--binanceChainId", chain)

    def limit_sell(self, trigger, qty, from_token, to_token, chain=BSC):
        return self.run("limit-order", "sell", "--triggerPrice", str(trigger), "--fromTokenQty", str(qty),
                        "--fromToken", from_token, "--toToken", to_token, "--binanceChainId", chain)

    # ---------------------------------------------------------- whales
    def tracker_group_create(self, name, chain=BSC):
        return self.run("tracker", "group", "create", "-c", chain, "-n", name)

    def tracker_add(self, group_id, address, label, chain=BSC):
        return self.run("tracker", "address", "add", "-c", chain, "-g", str(group_id), "-a", address, "--label", label)

    def tracker_tx(self, group_id=None, tag_type=None, chain=BSC):
        a = ["tracker", "tx", "query", "-c", chain]
        a += ["--group-id", str(group_id)] if group_id is not None else ["--tag-type", tag_type or "smy"]
        return self.run(*a)

    def leaderboard_analyze(self, address, chain=BSC):
        return self.run("leaderboard", "analyze", "-c", chain, "-a", address)

    def smart_money_signals(self, chain=BSC):
        return self.run("signal", "list", "-c", chain, "--source", "smart-money")

    # ---------------------------------------------------------- x402
    def x402_preview(self, url):
        return self.run("x402-payment", "preview", "--url", url)

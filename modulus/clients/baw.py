"""Binance Agentic Wallet (`baw` CLI) adapter - the AI execution layer.

Rewritten against the official Agentic Wallet docs + binance-agentic-wallet SKILL.md (Oct 2026).

Install (official):
    npx skills add binance/binance-skills-hub/skills/binance-web3/binance-agentic-wallet
    # the skill auto-installs `baw` on first use; to pin it yourself:
    npm install -g @binance/agentic-wallet@1.10.0       # = SKILL.md metadata.requiredCliVersion
Sign in (two commands, QR + 6-digit pairing code confirmed in the Binance App):
    baw auth signin --json                              # -> urlForWeb, qrCodeId, pairingCode, expireAt
    baw auth verify --qrCodeId <qrCodeId> --json        # blocks until confirmed (<= 5 min)
    baw wallet status --json                            # source of truth: data.status == CONNECTED

Every call appends --json. Envelope: {"success": true, "data": {...}} or
{"success": false, "error": {"code": int, "name": str, "message": str}}. Errors are relayed verbatim.
"""
from __future__ import annotations
import base64, json, os, shutil, subprocess, time
from ..config import BSC

REQUIRED_CLI = "1.10.0"   # binance-agentic-wallet SKILL.md v1.12.0 -> requiredCliVersion


class BawError(RuntimeError):
    def __init__(self, message: str, code=None, name=None, payload=None):
        super().__init__(message)
        self.code, self.name, self.payload = code, name, payload


class Baw:
    def __init__(self, binary: str = "baw", timeout: int = 90):
        self.bin, self.timeout = binary, timeout
        # npm installs the CLI on Windows as `baw.cmd` (plus `baw`/`baw.ps1`); a bare `subprocess.run(["baw", ...])`
        # cannot launch a .cmd (CreateProcess only auto-appends .exe, ignoring PATHEXT) -> WinError 2.
        # Resolve to the full path via PATHEXT so live execution works everywhere.
        self._exe = shutil.which(binary) or binary if os.name == "nt" else binary

    @property
    def available(self) -> bool:
        return shutil.which(self.bin) is not None

    # ------------------------------------------------------------------ core
    def run(self, *args: str, timeout: int | None = None) -> dict:
        cmd = [self._exe, *[str(a) for a in args], "--json"]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout or self.timeout)
        out = (p.stdout or "").strip()
        try:
            data = json.loads(out) if out else {}
        except json.JSONDecodeError:
            raise BawError(out or p.stderr or f"baw exited {p.returncode}")
        if isinstance(data, dict) and data.get("success") is False:
            err = data.get("error") or {}
            raise BawError(err.get("message") or json.dumps(data)[:500], err.get("code"), err.get("name"), data)
        if p.returncode != 0:      # exit codes are not documented; treat non-zero as failure, verbatim
            raise BawError((p.stderr or out or f"baw exited {p.returncode}")[:500], payload=data)
        return data

    @staticmethod
    def data(r: dict):
        return (r or {}).get("data")

    # ------------------------------------------------------------------ preflight / auth
    def cli_check(self, required: str = REQUIRED_CLI):
        return self.run("cli-check", "--required-version", required)          # data.needUpdateCli

    def skill_check(self, current_version: str):
        return self.run("skill-check", "--skill-name", "binance-agentic-wallet", "--current-version", current_version)

    def auth_signin(self):
        return self.run("auth", "signin")       # data.urlForWeb / qrCodeId / pairingCode, or status ALREADY_CONNECTED

    def auth_verify(self, qr_code_id: str):
        return self.run("auth", "verify", "--qrCodeId", qr_code_id, timeout=330)   # blocks <= 5 min

    def auth_signout(self):
        return self.run("auth", "signout")

    def preflight(self) -> dict:
        """Fail-closed readiness check for an unattended run. Returns a summary dict, raises BawError if not ready."""
        cc = self.data(self.cli_check()) or {}
        if cc.get("needUpdateCli"):
            raise BawError(f"baw {cc.get('currentCliVersion')} < {REQUIRED_CLI}: npm install -g @binance/agentic-wallet@{REQUIRED_CLI}")
        st = (self.data(self.status()) or {}).get("status")
        if st != "CONNECTED":
            raise BawError(f"wallet status {st}: run `baw auth signin --json` then `baw auth verify --qrCodeId <id> --json`")
        s = self.data(self.settings()) or {}
        return {"cli": cc.get("currentCliVersion"), "status": st,
                "dailyLimit": s.get("dailyLimit"), "quotaLeft": s.get("quotaLeft"),
                "abnormalTxnHandling": s.get("abnormalTxnHandling"), "tradeAllTokens": s.get("tradeAllTokens"),
                "x402QuotaLeft": s.get("x402QuotaLeft"), "sessionExpireTime": s.get("sessionExpireTime"),
                "inactiveSignOutTime": s.get("inactiveSignOutTime")}

    # ------------------------------------------------------------------ wallet (read-only)
    def status(self):     return self.run("wallet", "status")       # data.status: UNCONNECTED|CREATING|CONNECTED
    def chains(self):     return self.run("wallet", "chains")
    def settings(self):   return self.run("wallet", "settings")     # read-only; change in Binance App only

    def address(self, chain: str = BSC) -> str | None:
        for a in (self.data(self.run("wallet", "address")) or {}).get("addresses", []):
            if str(a.get("binanceChainId")) == str(chain):
                return a.get("address")
        return None

    def balance(self, token_address: str | None = None, symbol: str | None = None, chain: str = BSC):
        a = ["wallet", "balance", "--binanceChainId", chain]
        if token_address:
            a += ["--tokenAddress", token_address]
        if symbol:
            a += ["--symbol", symbol]
        return self.run(*a)          # data: [{symbol,address,binanceChainId,balance,price,value}] (hides < $0.01)

    def token_qty(self, token_address: str, chain: str = BSC) -> float:
        rows = self.data(self.balance(token_address=token_address, chain=chain)) or []
        return sum(float(r.get("balance") or 0) for r in rows
                   if str(r.get("address", "")).lower() == token_address.lower())

    def tx_lock(self, chain: str = BSC):
        return self.run("wallet", "tx-lock", "--binanceChainId", chain)   # data.status: UNLOCKED|LOCKED

    def is_locked(self, chain: str = BSC) -> bool:
        return (self.data(self.tx_lock(chain)) or {}).get("status") == "LOCKED"

    def tx_history(self, tx: str | None = None, tx_type: str | None = None, chain: str | None = None, size: int = 20):
        a = ["wallet", "tx-history", "--size", str(size)]
        if tx:
            a += ["--tx", tx]
        if tx_type:
            a += ["--type", tx_type]          # all | pending | confirmed
        if chain:
            a += ["--binanceChainId", chain]
        return self.run(*a)

    # ------------------------------------------------------------------ market orders
    def quote(self, qty, from_token, to_token, slippage="auto", chain: str = BSC):
        """data: {fromCoinSymbol, fromCoinAmount, toCoinSymbol, toCoinAmount, slippage(fraction)}. No priceImpact field."""
        return self.run("market-order", "quote", "--fromTokenQty", str(qty), "--fromToken", from_token,
                        "--toToken", to_token, "--binanceChainId", chain, "--slippage", str(slippage))

    @staticmethod
    def quote_price(q: dict, buy: bool) -> float | None:
        """USD-per-token implied by a quote (stablecoin leg ~ $1)."""
        d = (q or {}).get("data") or {}
        try:
            fa, ta = float(d["fromCoinAmount"]), float(d["toCoinAmount"])
        except (KeyError, TypeError, ValueError):
            return None
        if fa <= 0 or ta <= 0:
            return None
        return fa / ta if buy else ta / fa

    def swap(self, qty, from_token, to_token, slippage="auto", mev=True, gas_level="MEDIUM", chain: str = BSC):
        """data.orderId - SUBMITTED only, not a fill. Always follow with wait_market_order()."""
        return self.run("market-order", "swap", "--fromTokenQty", str(qty), "--fromToken", from_token,
                        "--toToken", to_token, "--binanceChainId", chain, "--slippage", str(slippage),
                        "--mev", "true" if mev else "false", "--gasLevel", gas_level)

    def market_order(self, order_id) -> dict:
        r = self.run("market-order", "list", "--orderId", str(order_id))
        items = (self.data(r) or {}).get("list") or []
        return items[0] if items else {}

    def wait_market_order(self, order_id, timeout_s: int = 120, every_s: int = 4) -> dict:
        """Poll to FINISHED/FAILED. On timeout report PENDING (still processing), never success."""
        t0, last = time.time(), {}
        while time.time() - t0 < timeout_s:
            last = self.market_order(order_id)
            if last.get("status") in ("FINISHED", "FAILED"):
                return last
            time.sleep(every_s)
        return {**last, "status": last.get("status") or "PENDING", "orderId": str(order_id), "timedOut": True}

    # ------------------------------------------------------------------ limit orders (BSC + Solana only)
    def limit_buy(self, trigger, qty, from_token, to_token, slippage="auto", mev=True, gas_level="MEDIUM", chain: str = BSC):
        """Buy `to_token` with `qty` of from_token (USDT/USDC/native) when its USD price DROPS to `trigger`. -> data.strategyId"""
        return self.run("limit-order", "buy", "--triggerPrice", str(trigger), "--fromTokenQty", str(qty),
                        "--fromToken", from_token, "--toToken", to_token, "--binanceChainId", chain,
                        "--slippage", str(slippage), "--mev", "true" if mev else "false", "--gasLevel", gas_level)

    def limit_sell(self, trigger, qty, from_token, to_token, slippage="auto", mev=True, gas_level="MEDIUM", chain: str = BSC):
        """Sell `qty` of from_token for to_token (USDT/USDC/native) when its USD price REACHES `trigger`. -> data.strategyId"""
        return self.run("limit-order", "sell", "--triggerPrice", str(trigger), "--fromTokenQty", str(qty),
                        "--fromToken", from_token, "--toToken", to_token, "--binanceChainId", chain,
                        "--slippage", str(slippage), "--mev", "true" if mev else "false", "--gasLevel", gas_level)

    def limit_order(self, strategy_id) -> dict:
        items = (self.data(self.run("limit-order", "list", "--strategyId", str(strategy_id))) or {}).get("list") or []
        return items[0] if items else {}

    def limit_orders(self, status: str | None = None, chain: str = BSC, page_size: int = 100) -> list:
        a = ["limit-order", "list", "--binanceChainId", chain, "--pageSize", str(page_size)]
        if status:
            a += ["--status", status]   # WORKING|TRIGGERED|PENDING|FINISHED|FAILED|EXPIRED|CANCELED
        return (self.data(self.run(*a)) or {}).get("list") or []

    def limit_cancel(self, strategy_id):
        return self.run("limit-order", "cancel", "--strategyId", str(strategy_id))

    # ------------------------------------------------------------------ whales / signals (binance-wallet-tracker, -leaderboard, -trading-signal)
    # These are NOT core `baw` subcommands (baw: auth|wallet|approvals|market-order|limit-order|
    # contract-call|sign-message|prediction|x402-payment|defi|skill-check|cli-check). `tracker`,
    # `leaderboard` and `signal` are separate wallet-skills; they only resolve when those skills
    # are installed. Callers (Executors/elders) must treat failure as "elder abstains" - never a crash.
    def tracker_group_create(self, name, chain: str = BSC):
        """wallet-skill `binance-wallet-tracker` (not a core baw subcommand): may be unavailable unless installed."""
        return self.run("tracker", "group", "create", "-c", chain, "-n", name)

    def tracker_add(self, group_id, address, label, chain: str = BSC):
        """wallet-skill `binance-wallet-tracker` (not a core baw subcommand): may be unavailable unless installed."""
        return self.run("tracker", "address", "add", "-c", chain, "-g", str(group_id), "-a", address, "--label", label)

    def tracker_tx(self, group_id=None, tag_type=None, trade_side=None, min_value=None, chain: str = BSC):
        """wallet-skill `binance-wallet-tracker` (not a core baw subcommand); may be unavailable unless installed.

        Public mode (--tag-type smy|kol) needs no sign-in; --group-id needs a session. No pagination, no ca filter.
        """
        a = ["tracker", "tx", "query", "-c", chain]
        a += ["--group-id", str(group_id)] if group_id is not None else ["--tag-type", tag_type or "smy"]
        if trade_side:
            a += ["--trade-side", trade_side]          # "19,11" buys, "29,21" sells
        if min_value is not None:
            a += ["--min-value", str(min_value)]
        return self.run(*a)

    def tracker_token(self, tag_type="smy", period="24h", chain: str = BSC):
        """wallet-skill `binance-wallet-tracker` (not a core baw subcommand): may be unavailable unless installed."""
        return self.run("tracker", "token", "query", "-c", chain, "--tag-type", tag_type, "--period", period)

    def smart_money_flow(self, addresses: set[str], chain: str = BSC, tag_type="smy") -> dict:
        """wallet-skill `binance-wallet-tracker` (not a core baw subcommand): may be unavailable unless installed.

        {token_address_lower: net in [-1,1]} = (buyUSD - sellUSD)/(buyUSD + sellUSD) over the public SMY tape.
        Treat a missing skill / raised BawError as "elder abstains".
        """
        rows = self.data(self.tracker_tx(tag_type=tag_type, chain=chain)) or []
        rows = rows if isinstance(rows, list) else (rows.get("list") or [])
        agg: dict[str, list[float]] = {}
        for r in rows:
            ca = str(r.get("ca", "")).lower()
            if ca not in addresses:
                continue
            side, usd = r.get("tradeSideCategory"), float(r.get("txUsdValue") or 0)
            b_s = agg.setdefault(ca, [0.0, 0.0])
            if side in (11, 19):
                b_s[0] += usd
            elif side in (21, 29):
                b_s[1] += usd               # undocumented side codes are ignored (skill: filter defensively)
        return {ca: (b - s) / (b + s) for ca, (b, s) in agg.items() if b + s > 0}

    def leaderboard_analyze(self, address, chain: str = BSC):
        """wallet-skill `binance-wallet-leaderboard` (not a core baw subcommand): may be unavailable unless installed."""
        return self.run("leaderboard", "analyze", "-c", chain, "-a", address)

    def smart_money_signals(self, chain: str = BSC, time_range: str | None = None):
        """wallet-skill `binance-wallet-trading-signal` (not a core baw subcommand): may be unavailable unless installed."""
        a = ["signal", "list", "-c", chain, "--source", "smart-money"]
        if time_range:
            a += ["--time-range", time_range]
        return self.run(*a)

    # ------------------------------------------------------------------ x402 (v2 only; BSC, Base, Solana)
    def x402_preview(self, payment_required):
        """payment_required = the base64 PAYMENT-REQUIRED header value, or the decoded dict/JSON string."""
        pr = payment_required if isinstance(payment_required, str) else json.dumps(payment_required)
        return self.run("x402-payment", "preview", "--paymentRequirements", pr)   # data.paymentId, data.options[]

    def x402_sign(self, payment_id: str, selected_index: int):
        """-> data.paymentHeaderName ('PAYMENT-SIGNATURE'), paymentHeaderValue, signatureExpiresAt. Replay immediately."""
        return self.run("x402-payment", "sign", "--paymentId", payment_id, "--selectedIndex", str(selected_index))

    def x402_pay_header(self, payment_required, prefer=("U", "USD1", "USDC", "USDT")) -> tuple[str, str]:
        """preview -> pick a READY_TO_SIGN option (U/USD1 need no Permit2 approval) -> sign. Caller must have consent."""
        d = self.data(self.x402_preview(payment_required)) or {}
        ready = [o for o in d.get("options", []) if o.get("status") == "READY_TO_SIGN"]
        if not ready:
            raise BawError("no READY_TO_SIGN x402 option", payload=d)
        ready.sort(key=lambda o: prefer.index(o.get("tokenSymbol")) if o.get("tokenSymbol") in prefer else 99)
        s = self.data(self.x402_sign(d["paymentId"], ready[0]["index"])) or {}
        return s["paymentHeaderName"], s["paymentHeaderValue"]

    @staticmethod
    def decode_payment_required(header_value: str) -> dict:
        return json.loads(base64.b64decode(header_value))

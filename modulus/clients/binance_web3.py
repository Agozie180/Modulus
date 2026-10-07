"""Signed client for the Binance Web3 API (https://web3.binance.com/build).

Covers every module the hackathon lists: RWA Data, Market, Trading, Transaction,
Wallet, Address Portfolio, DeFi data + DeFi transaction building, and b402.

Signing: X-OC-SIGN = Base64(HMAC_SHA256(secret, timestamp + METHOD + requestPath + payload))
where requestPath includes the `/build` prefix and, for GET, the raw query string
("?a=1&b=2"); for POST, payload is the exact JSON body. The docs state that /build
must be inside the signed path and that the exact raw query string is signed
(Trading API "Common Pitfalls", error 40102). See docs/DX_REPORT_DRAFT.md.
"""
from __future__ import annotations
import base64, hashlib, hmac, json, time, uuid
import urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone
from typing import Any

from ..config import SETTINGS, BSC


class Web3ApiError(RuntimeError):
    def __init__(self, code: Any, msg: str, path: str):
        super().__init__(f"[{code}] {msg} ({path})")
        self.code, self.msg, self.path = code, msg, path


def iso_ms_now() -> str:
    now = datetime.now(timezone.utc)                     # one clock read (audit #15)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def sign(secret: str, timestamp: str, method: str, request_path: str, payload: str = "") -> str:
    prehash = f"{timestamp}{method.upper()}{request_path}{payload}"
    mac = hmac.new(secret.encode(), prehash.encode(), hashlib.sha256).digest()
    return base64.b64encode(mac).decode()


class BinanceWeb3:
    RETRYABLE = {429, 500, 502, 503, 504}
    # Business errors arrive inside HTTP 200 bodies (docs: "All responses - including errors - return HTTP 200")
    RETRY_CODES = {"42900", "50000", "50001", "40465", "40432"}
    OK = (0, "0")
    B402_OK = ("000000000", 0, "0")

    def __init__(self, settings=SETTINGS, timeout: float = 20.0):
        self.s = settings
        self.timeout = timeout
        parsed = urllib.parse.urlparse(self.s.base_url)
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.prefix = parsed.path.rstrip("/")  # "/build"

    # ------------------------------------------------------------------ core
    def build_request(self, method: str, path: str, params: dict | None = None, body: Any = None,
                      ts: str | None = None) -> tuple[str, dict, bytes | None]:
        """Returns (url, headers, data). The signed requestPath = /build + path + raw query string
        (for GET and for POSTs that also carry query params); payload = exact JSON body bytes."""
        query = ""
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                query = "?" + urllib.parse.urlencode(clean, quote_via=urllib.parse.quote)   # %20, never '+'
        payload = json.dumps(body, separators=(",", ":")) if body is not None else ""
        request_path = f"{self.prefix}{path}{query}"
        ts = ts or iso_ms_now()
        headers = {
            "X-OC-APIKEY": self.s.api_key or "",
            "X-OC-TIMESTAMP": ts,
            "X-OC-SIGN": sign(self.s.api_secret or "", ts, method, request_path, payload if method != "GET" else ""),
            "X-OC-RECV-WINDOW": str(getattr(self.s, "recv_window_ms", 10000)),
            "X-OC-NONCE": uuid.uuid4().hex,
            "Content-Type": "application/json",
            "User-Agent": "modulus/2.0",
        }
        return self.origin + request_path, headers, (payload.encode() if method != "GET" and payload else None)

    def _request(self, method: str, path: str, params: dict | None = None, body: Any = None,
                 retries: int = 3, ok_codes: tuple = OK) -> Any:
        if not self.s.has_api_key:
            raise Web3ApiError("NO_KEY", "BINANCE_WEB3_API_KEY/SECRET not set (read-only public mode available)", path)
        last: Exception | None = None
        for attempt in range(retries):
            url, headers, data = self.build_request(method, path, params, body)
            req = urllib.request.Request(url, method=method, headers=headers, data=data)
            wait = 0.6 * 2 ** attempt
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    out = json.load(r)
                if out.get("code") not in ok_codes:
                    err = Web3ApiError(out.get("code"), out.get("msg") or out.get("message", ""), path)
                    if str(out.get("code")) in self.RETRY_CODES and attempt < retries - 1:
                        last = err; time.sleep(wait); continue
                    raise err
                return out.get("data")
            except urllib.error.HTTPError as e:
                raw = e.read().decode(errors="ignore")
                try:
                    j = json.loads(raw)
                    last = Web3ApiError(j.get("code", e.code), j.get("msg") or j.get("message") or raw[:300], path)
                except ValueError:
                    last = Web3ApiError(e.code, raw[:300], path)
                if e.code not in self.RETRYABLE:
                    raise last
                ra = e.headers.get("Retry-After") if e.headers else None
                if ra and ra.replace(".", "", 1).isdigit():
                    wait = float(ra)
            except (urllib.error.URLError, TimeoutError) as e:
                last = e
            time.sleep(wait)
        raise last  # type: ignore[misc]

    def get(self, path, **params):
        return self._request("GET", path, params=params)

    def post(self, path, body, retries: int = 3, **params):
        return self._request("POST", path, params=params or None, body=body, retries=retries)

    # ------------------------------------------------------------ RWA Data
    def rwa_platforms(self, platform_id=None):
        return self.get("/api/v1/dex/market/rwa/platforms", platformId=platform_id)

    def rwa_tokens(self, platform_id=None, tab_id=None, chain=BSC):
        return self.get("/api/v1/dex/market/rwa/tokens", binanceChainId=chain, platformId=platform_id, tabId=tab_id)

    def rwa_price(self, addresses: list[str], chain=BSC):
        out = []
        for i in range(0, len(addresses), 100):           # no silent truncation past 100
            out += self.get("/api/v1/dex/market/rwa/price", binanceChainId=chain,
                            tokenContractAddresses=",".join(addresses[i:i + 100])) or []
        return out

    def rwa_search(self, keyword, platform_id=None):
        return self.get("/api/v1/dex/market/rwa/search", keyword=keyword, platformId=platform_id)

    def rwa_profile(self, address, chain=BSC):
        return self.get("/api/v1/dex/market/rwa/underlying-profile", binanceChainId=chain, tokenContractAddress=address)

    def rwa_underlying_market(self, address, chain=BSC):
        return self.get("/api/v1/dex/market/rwa/underlying-market", binanceChainId=chain, tokenContractAddress=address)

    # -------------------------------------------------------------- Market
    def price_info(self, addresses, chain=BSC):
        """Batched: up to 100 tokens per call."""
        addresses = [addresses] if isinstance(addresses, str) else list(addresses)
        out = []
        for i in range(0, len(addresses), 100):
            out += self.post("/api/v1/dex/market/price-info",
                             [{"binanceChainId": chain, "tokenContractAddress": a} for a in addresses[i:i + 100]]) or []
        return out

    def candles(self, address, bar="1h", limit=300, chain=BSC):
        """Rows are [open, high, low, close, volume, ts, tradeCount] (NOT the Spot [ts, o, h, l, c] layout)."""
        return self.get("/api/v1/dex/market/candles", binanceChainId=chain, tokenContractAddress=address, bar=bar, limit=limit)

    @staticmethod
    def candles_to_spot_layout(rows):
        """Re-order Market API candles into [ts, o, h, l, c, vol] so the elders can use either source."""
        return sorted([[int(r[5]), r[0], r[1], r[2], r[3], r[4]] for r in rows or []])

    def holders(self, address, chain=BSC):
        return self.get("/api/v1/dex/market/token/holder", binanceChainId=chain, tokenContractAddress=address)

    def top_traders(self, address, chain=BSC):
        return self.get("/api/v1/dex/market/token/top-trader", binanceChainId=chain, tokenContractAddress=address)

    def top_liquidity(self, address, chain=BSC):
        return self.get("/api/v1/dex/market/token/top-liquidity", binanceChainId=chain, tokenContractAddress=address)

    def trades(self, address, chain=BSC, limit=100):
        return self.get("/api/v1/dex/market/trades", binanceChainId=chain, tokenContractAddress=address, limit=limit)

    def tracked_trades(self, tracker_type, chain=BSC, **kw):
        """trackerType is required by the API (see docs: address-tracker/trades)."""
        return self.get("/api/v1/dex/market/address-tracker/trades", trackerType=tracker_type, binanceChainId=chain, **kw)

    # --------------------------------------------------- Address portfolio
    def portfolio_overview(self, address, chain=BSC, time_frame="1"):
        """timeFrame required: "1"=1D "2"=7D "3"=1M "4"=3M. EVM addresses must be lowercase."""
        return self.get("/api/v1/dex/market/portfolio/overview", binanceChainId=chain,
                        walletAddress=address.lower(), timeFrame=time_frame)

    def token_pnl(self, wallet, token, chain=BSC):
        return self.get("/api/v1/dex/market/portfolio/token/latest-pnl", binanceChainId=chain,
                        walletAddress=wallet.lower(), tokenContractAddress=token.lower())

    # ------------------------------------------------------------- Trading
    def approve_tx(self, token, amount_wei, vendor=None, chain=BSC):
        return self.get("/api/v1/dex/aggregator/approve-transaction", binanceChainId=chain,
                        tokenContractAddress=token, approveAmount=str(amount_wei), vendor=vendor)

    def quote(self, from_token, to_token, amount_wei, wallet=None, chain=BSC):
        return self.get("/api/v1/dex/aggregator/quote", binanceChainId=chain, fromTokenAddress=from_token,
                        toTokenAddress=to_token, amount=str(amount_wei), userWalletAddress=wallet)

    def swap(self, quote_id, from_token, to_token, amount_wei, wallet, slippage_pct=1.0, chain=BSC,
             price_impact_pct=None):
        """quoteId TTL is 30 s: call within 30 s of /quote, re-quote on 40401."""
        return self.get("/api/v1/dex/aggregator/swap", quoteId=quote_id, binanceChainId=chain,
                        fromTokenAddress=from_token, toTokenAddress=to_token, amount=str(amount_wei),
                        userWalletAddress=wallet, slippagePercent=str(slippage_pct),
                        priceImpactProtectionPercent=None if price_impact_pct is None else str(price_impact_pct))

    def history(self, tx_hash, chain=BSC):
        return self.get("/api/v1/dex/aggregator/history", binanceChainId=chain, txHash=tx_hash)

    def rfq_submit(self, user_signature, vendor, rfq_order_id, request_id, signing_scheme=None):
        body = {"requestId": request_id, "userSignature": user_signature, "vendor": vendor, "quoteId": rfq_order_id}
        if signing_scheme:
            body["signingScheme"] = signing_scheme
        return self.post("/api/v1/dex/aggregator/order/submit", body, retries=1)   # same requestId on caller retry

    def rfq_status(self, order_id):
        return self.get(f"/api/v1/dex/aggregator/order/{order_id}")

    # --------------------------------------------------------- Transaction
    def gas_price(self, chain=BSC):
        return self.get("/api/v1/dex/pre-transaction/gas-price", binanceChainId=chain)

    @staticmethod
    def _evm_tx(frm, to, data, value="0"):
        return {"from": frm, "to": to, "value": str(int(str(value or "0"), 0)), "data": data or "0x"}

    def simulate(self, frm: str, to: str, data: str, value: str = "0", chain=BSC):
        """Docs: binanceChainId + evmTx {from,to,value,data}. -> status SUCCESS|FAIL, failReason, allowanceChanges."""
        return self.post("/api/v1/dex/pre-transaction/simulate", {"binanceChainId": chain, "evmTx": self._evm_tx(frm, to, data, value)})

    def gas_limit(self, frm: str, to: str, data: str, value: str = "0", chain=BSC):
        return self.post("/api/v1/dex/pre-transaction/gas-limit", {"binanceChainId": chain, "evmTx": self._evm_tx(frm, to, data, value)})

    def broadcast(self, signed_tx, address, mev=True, chain=BSC):
        return self.post("/api/v1/dex/pre-transaction/broadcast-transaction", {
            "binanceChainId": chain, "signedTransaction": signed_tx, "address": address, "enableMevProtection": mev},
            retries=1)

    # -------------------------------------------------------------- Wallet
    def balances(self, address, chain=BSC):
        return self.get("/api/v1/dex/balance/all-token-balances-by-address", address=address, chains=chain)

    def tx_detail(self, tx_hash, chain=BSC):
        return self.get("/api/v1/dex/post-transaction/transaction-detail-by-txhash", binanceChainId=chain, txHash=tx_hash)

    # ---------------------------------------------------------------- DeFi
    def defi_investments(self, token=None, chain=BSC, invest_type="Earn", protocol=None, page=1, size=20):
        """investType required (Earn | LiquidityPool). Docs list no bStock lending; idle USDT -> Venus Earn."""
        body = {"investType": invest_type, "binanceChainId": chain, "page": page, "size": size}
        if token:
            body["tokenAddressList"] = [token]
        if protocol:
            body["defiProtocolId"] = protocol
        return self.post("/api/v1/defi/data/investment/list", body)

    def defi_deposit(self, body: dict):
        return self.post("/api/v1/defi/transaction/deposit", body)

    # ---------------------------------------------------------------- b402 (x402 V2 facilitator)
    # Body is the outer envelope {"body": <inner x402 object>}; success code is "000000000".
    def _b402(self, operation: str, inner: dict) -> dict:
        return self._request("POST", f"/api/v2/b402/{operation}", body={"body": inner}, ok_codes=self.B402_OK)

    def b402_supported(self) -> dict:            # -> {"kinds": [...], "extensions": ..., "signers": ...}
        return self._b402("supported", {})

    def b402_verify(self, inner: dict) -> dict:  # inner = {x402Version:2, paymentPayload, paymentRequirements}
        return self._b402("verify", inner)

    def b402_settle(self, inner: dict, settle_amount: str | None = None) -> dict:
        if settle_amount is not None:            # permit2-upto only
            inner = {**inner, "settleAmount": str(settle_amount)}
        return self._b402("settle", inner)

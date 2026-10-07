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
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(time.time()*1000)%1000:03d}Z"


def sign(secret: str, timestamp: str, method: str, request_path: str, payload: str = "") -> str:
    prehash = f"{timestamp}{method.upper()}{request_path}{payload}"
    mac = hmac.new(secret.encode(), prehash.encode(), hashlib.sha256).digest()
    return base64.b64encode(mac).decode()


class BinanceWeb3:
    RETRYABLE = {429, 500, 502, 503, 504}

    def __init__(self, settings=SETTINGS, timeout: float = 20.0):
        self.s = settings
        self.timeout = timeout
        parsed = urllib.parse.urlparse(self.s.base_url)
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.prefix = parsed.path.rstrip("/")  # "/build"

    # ------------------------------------------------------------------ core
    def _request(self, method: str, path: str, params: dict | None = None, body: dict | None = None,
                 retries: int = 3) -> Any:
        if not self.s.has_api_key:
            raise Web3ApiError("NO_KEY", "BINANCE_WEB3_API_KEY/SECRET not set (read-only public mode available)", path)
        query = ""
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            query = "?" + urllib.parse.urlencode(clean)
        payload = json.dumps(body, separators=(",", ":")) if body is not None else ""
        request_path = f"{self.prefix}{path}{query if method == 'GET' else ''}"
        last: Exception | None = None
        for attempt in range(retries):
            ts = iso_ms_now()
            headers = {
                "X-OC-APIKEY": self.s.api_key,
                "X-OC-TIMESTAMP": ts,
                "X-OC-SIGN": sign(self.s.api_secret, ts, method, request_path, payload if method != "GET" else ""),
                "X-OC-RECV-WINDOW": "10000",
                "X-OC-NONCE": uuid.uuid4().hex,
                "Content-Type": "application/json",
                "User-Agent": "modulus/1.0",
            }
            req = urllib.request.Request(self.origin + request_path, method=method, headers=headers,
                                         data=payload.encode() if method != "GET" and payload else None)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    out = json.load(r)
                if out.get("code") not in (0, "0"):
                    raise Web3ApiError(out.get("code"), out.get("msg", ""), path)
                return out.get("data")
            except urllib.error.HTTPError as e:
                last = Web3ApiError(e.code, e.read().decode(errors="ignore")[:300], path)
                if e.code not in self.RETRYABLE:
                    raise last
            except (urllib.error.URLError, TimeoutError) as e:
                last = e
            time.sleep(0.6 * 2 ** attempt)
        raise last  # type: ignore[misc]

    def get(self, path, **params):
        return self._request("GET", path, params=params)

    def post(self, path, body):
        return self._request("POST", path, body=body)

    # ------------------------------------------------------------ RWA Data
    def rwa_platforms(self, platform_id=None):
        return self.get("/api/v1/dex/market/rwa/platforms", platformId=platform_id)

    def rwa_tokens(self, platform_id=None, tab_id=None, chain=BSC):
        return self.get("/api/v1/dex/market/rwa/tokens", binanceChainId=chain, platformId=platform_id, tabId=tab_id)

    def rwa_price(self, addresses: list[str], chain=BSC):
        return self.get("/api/v1/dex/market/rwa/price", binanceChainId=chain, tokenContractAddresses=",".join(addresses[:100]))

    def rwa_search(self, keyword, platform_id=None):
        return self.get("/api/v1/dex/market/rwa/search", keyword=keyword, platformId=platform_id)

    def rwa_profile(self, address, chain=BSC):
        return self.get("/api/v1/dex/market/rwa/underlying-profile", binanceChainId=chain, tokenContractAddress=address)

    def rwa_underlying_market(self, address, chain=BSC):
        return self.get("/api/v1/dex/market/rwa/underlying-market", binanceChainId=chain, tokenContractAddress=address)

    # -------------------------------------------------------------- Market
    def price_info(self, address, chain=BSC):
        return self.post("/api/v1/dex/market/price-info", [{"binanceChainId": chain, "tokenContractAddress": address}])

    def candles(self, address, bar="1H", limit=300, chain=BSC):
        return self.get("/api/v1/dex/market/candles", binanceChainId=chain, tokenContractAddress=address, bar=bar, limit=limit)

    def holders(self, address, chain=BSC):
        return self.get("/api/v1/dex/market/token/holder", binanceChainId=chain, tokenContractAddress=address)

    def top_traders(self, address, chain=BSC):
        return self.get("/api/v1/dex/market/token/top-trader", binanceChainId=chain, tokenContractAddress=address)

    def top_liquidity(self, address, chain=BSC):
        return self.get("/api/v1/dex/market/token/top-liquidity", binanceChainId=chain, tokenContractAddress=address)

    def trades(self, address, chain=BSC, limit=100):
        return self.get("/api/v1/dex/market/trades", binanceChainId=chain, tokenContractAddress=address, limit=limit)

    def tracked_trades(self, **kw):
        return self.get("/api/v1/dex/market/address-tracker/trades", **kw)

    # --------------------------------------------------- Address portfolio
    def portfolio_overview(self, address, chain=BSC):
        return self.get("/api/v1/dex/market/portfolio/overview", binanceChainId=chain, walletAddress=address)

    def token_pnl(self, wallet, token, chain=BSC):
        return self.get("/api/v1/dex/market/portfolio/token/latest-pnl", binanceChainId=chain, walletAddress=wallet, tokenContractAddress=token)

    # ------------------------------------------------------------- Trading
    def approve_tx(self, token, amount_wei, vendor=None, chain=BSC):
        return self.get("/api/v1/dex/aggregator/approve-transaction", binanceChainId=chain,
                        tokenContractAddress=token, approveAmount=str(amount_wei), vendor=vendor)

    def quote(self, from_token, to_token, amount_wei, wallet=None, chain=BSC):
        return self.get("/api/v1/dex/aggregator/quote", binanceChainId=chain, fromTokenAddress=from_token,
                        toTokenAddress=to_token, amount=str(amount_wei), userWalletAddress=wallet)

    def swap(self, quote_id, from_token, to_token, amount_wei, wallet, slippage_pct=1.0, chain=BSC):
        return self.get("/api/v1/dex/aggregator/swap", quoteId=quote_id, binanceChainId=chain,
                        fromTokenAddress=from_token, toTokenAddress=to_token, amount=str(amount_wei),
                        userWalletAddress=wallet, slippagePercent=slippage_pct)

    def rfq_submit(self, user_signature, vendor, rfq_order_id, request_id=None):
        return self.post("/api/v1/dex/aggregator/order/submit", {
            "userSignature": user_signature, "vendor": vendor, "quoteId": rfq_order_id,
            "requestId": request_id or str(uuid.uuid4())})

    def rfq_status(self, order_id):
        return self.get(f"/api/v1/dex/aggregator/order/{order_id}")

    # --------------------------------------------------------- Transaction
    def gas_price(self, chain=BSC):
        return self.get("/api/v1/dex/pre-transaction/gas-price", binanceChainId=chain)

    def simulate(self, tx: dict, chain=BSC):
        return self.post("/api/v1/dex/pre-transaction/simulate", {"binanceChainId": chain, **tx})

    def broadcast(self, signed_tx, address, mev=True, chain=BSC):
        return self.post("/api/v1/dex/pre-transaction/broadcast-transaction", {
            "binanceChainId": chain, "signedTransaction": signed_tx, "address": address, "enableMevProtection": mev})

    # -------------------------------------------------------------- Wallet
    def balances(self, address, chain=BSC):
        return self.get("/api/v1/dex/balance/all-token-balances-by-address", binanceChainId=chain, address=address)

    def tx_detail(self, tx_hash, chain=BSC):
        return self.get("/api/v1/dex/post-transaction/transaction-detail-by-txhash", binanceChainId=chain, txHash=tx_hash)

    # ---------------------------------------------------------------- DeFi
    def defi_investments(self, token=None, chain=BSC):
        return self.post("/api/v1/defi/data/investment/list", {"binanceChainId": chain, "tokenContractAddress": token})

    def defi_deposit(self, body: dict):
        return self.post("/api/v1/defi/transaction/deposit", body)

    # ---------------------------------------------------------------- b402
    def b402_supported(self):
        return self.post("/api/v2/b402/supported", {})

    def b402_verify(self, payload: dict):
        return self.post("/api/v2/b402/verify", payload)

    def b402_settle(self, payload: dict):
        return self.post("/api/v2/b402/settle", payload)

"""Paid verdicts over HTTP 402 (x402 V2, settled by Binance B402).

GET /verdict/{ticker}
  * no PAYMENT-SIGNATURE header -> 402 + PAYMENT-REQUIRED header (base64 PaymentRequired)
  * with PAYMENT-SIGNATURE      -> check accepted == server-held requirement,
    POST /build/api/v2/b402/verify, compute verdict, POST /build/api/v2/b402/settle,
    return 200 + PAYMENT-RESPONSE header (base64 SettlementResponse).
Bazaar metadata is attached to paymentPayload.extensions.bazaar on Settle so the
endpoint is indexed by B402 Bazaar after the first successful settlement.
"""
from __future__ import annotations
import base64, json, os, re, threading, time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from ..agent import Modulus
from ..clients.binance_web3 import BinanceWeb3, Web3ApiError

app = FastAPI(title="Modulus Council API", version="2.0")

NETWORK = "eip155:56"                                   # CAIP-2, BSC mainnet (eip155:97 = QA only)
PAY_TO = os.environ.get("MODULUS_B402_PAYTO", "")       # write-once payTo from Developer Portal B402 onboarding
PRICE_ATOMIC = os.getenv("MODULUS_PRICE_ATOMIC", str(10 ** 16))   # 0.01 of an 18-decimal stablecoin
PUBLIC_URL = os.getenv("MODULUS_PUBLIC_URL", "").rstrip("/")      # buyer-facing base URL
MAX_TIMEOUT = int(os.getenv("MODULUS_MAX_TIMEOUT_SECONDS", "300"))
# (asset, assetTransferMethod, scheme) in preference order. U / USD1 support EIP-3009
# (buyer needs no approval); USDT is Permit2-only (buyer needs a one-time Permit2 allowance).
OFFER = [
    ("0xcE24439F2D9C6a2289F741120FE202248B666666", "eip3009", "exact"),        # U, 18 dec
    ("0x8d0D000Ee44948FC98c9B98A4FA4921476f08B0d", "eip3009", "exact"),        # USD1, 18 dec
    ("0x55d398326f99059fF775485246999027B3197955", "permit2-exact", "exact"),  # USDT, 18 dec
]
TICKER = re.compile(r"^[A-Z.]{1,8}$")

api = BinanceWeb3()
_m: Modulus | None = None
_cache: dict = {"t": 0.0, "kinds": []}
_lock = threading.Lock()


def _b64(obj: dict) -> str:
    return base64.b64encode(json.dumps(obj, separators=(",", ":")).encode()).decode()


def _kinds() -> list[dict]:
    """POST /api/v2/b402/supported, cached 10 min. kinds[].extra is copied verbatim."""
    with _lock:
        if not _cache["kinds"] or time.time() - _cache["t"] > 600:
            data = api.b402_supported() or {}
            _cache.update(t=time.time(), kinds=data.get("kinds", []))
        return _cache["kinds"]


def _kind_asset(k: dict) -> str:
    # The docs do not publish per-kind fields beyond `extra`; check the live response once.
    e = k.get("extra") or {}
    return str(k.get("asset") or e.get("asset") or e.get("tokenAddress") or e.get("token") or "").lower()


def accepts() -> list[dict]:
    if not PAY_TO:
        raise RuntimeError("MODULUS_B402_PAYTO not set (use the payTo confirmed in B402 onboarding)")
    out = []
    for asset, method, scheme in OFFER:
        for k in _kinds():
            e = k.get("extra") or {}
            if (k.get("network") == NETWORK and k.get("scheme", scheme) == scheme
                    and e.get("assetTransferMethod") == method and _kind_asset(k) == asset.lower()):
                out.append({"scheme": scheme, "network": NETWORK, "amount": PRICE_ATOMIC, "asset": asset,
                            "payTo": PAY_TO, "maxTimeoutSeconds": MAX_TIMEOUT, "extra": dict(e)})
                break
    return out  # only combinations present in kinds[] are advertised


def resource(ticker: str, request: Request) -> dict:
    base = PUBLIC_URL or str(request.base_url).rstrip("/")
    return {"url": f"{base}/verdict/{ticker}",
            "description": f"Modulus Council verdict on {ticker} (bStocks/Ondo/xStocks on BSC)",
            "mimeType": "application/json"}


def bazaar(ticker: str) -> dict:
    return {
        "description": "Calibrated BUY/SELL/HOLD/VETO verdict on one tokenized US stock on BNB Chain, "
                       "with each elder's reasoning",
        "routeTemplate": "/verdict/:ticker",
        "info": {"input": {"type": "http", "method": "GET", "pathParams": {"ticker": ticker}},
                 "output": {"type": "json", "example": {"symbol": "NVDA", "action": "HOLD", "confidence": 0.61}}},
        "schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
            "properties": {
                "input": {"type": "object", "properties": {
                    "type": {"const": "http"}, "method": {"enum": ["GET"]},
                    "pathParams": {"type": "object",
                                   "properties": {"ticker": {"type": "string", "pattern": "^[A-Z.]{1,8}$"}},
                                   "required": ["ticker"]}},
                    "required": ["type", "method"]},
                "output": {"type": "object"}},
            "required": ["input"]},
    }


def payment_required(ticker: str, request: Request, error: str, reqs: list[dict]) -> JSONResponse:
    body = {"x402Version": 2, "error": error, "resource": resource(ticker, request),
            "accepts": reqs, "extensions": {"bazaar": bazaar(ticker)}}
    return JSONResponse(body, status_code=402, headers={"PAYMENT-REQUIRED": _b64(body)})


def _council(ticker: str) -> dict | None:
    global _m
    _m = _m or Modulus()
    res = _m.scan([ticker])
    return res["verdicts"][0].as_dict() if res["verdicts"] else None


@app.get("/health")
def health():
    return {"ok": True, "agent": "modulus", "pricing": "0.01 U / USD1 / USDT per verdict via B402 (x402 v2)"}


@app.get("/verdict/{ticker}")
def verdict(ticker: str, request: Request):          # sync def: runs in threadpool (blocking I/O inside)
    ticker = ticker.upper()
    if not TICKER.match(ticker):
        return JSONResponse({"error": "ticker must be a US stock symbol, e.g. NVDA"}, status_code=400)
    try:
        reqs = accepts()
    except (Web3ApiError, RuntimeError) as e:
        return JSONResponse({"error": f"payments unavailable: {e}"}, status_code=503)
    if not reqs:
        return JSONResponse({"error": "no B402 kind matches the configured assets"}, status_code=503)

    header = request.headers.get("PAYMENT-SIGNATURE") or request.headers.get("X-PAYMENT")  # X-PAYMENT = v1 legacy
    if not header:
        return payment_required(ticker, request, "PAYMENT-SIGNATURE header is required", reqs)
    try:
        payload = json.loads(base64.b64decode(header))
    except ValueError:
        return JSONResponse({"error": "malformed PAYMENT-SIGNATURE"}, status_code=400)
    if payload.get("x402Version") != 2:
        return payment_required(ticker, request, "invalid_x402_version", reqs)
    req = next((r for r in reqs if payload.get("accepted") == r), None)   # exact match with server-held requirement
    if req is None:
        return payment_required(ticker, request, "accepted does not match any offered requirement", reqs)

    payload = {**payload, "extensions": {**(payload.get("extensions") or {}), "bazaar": bazaar(ticker)}}
    inner = {"x402Version": 2, "paymentPayload": payload, "paymentRequirements": req}
    try:
        v = api.b402_verify(inner) or {}
    except Web3ApiError as e:
        return JSONResponse({"error": f"facilitator error {e.code}"}, status_code=502)
    if not v.get("isValid"):
        return payment_required(ticker, request, v.get("invalidReason", "invalid_payload"), reqs)

    out = _council(ticker)                      # produce the goods BEFORE moving money
    if out is None:
        return JSONResponse({"error": f"{ticker} has no bStock on BSC; you were not charged"}, status_code=404)

    try:
        s = api.b402_settle(inner) or {}        # idempotent for the same signed authorization
    except Web3ApiError as e:
        return JSONResponse({"error": f"facilitator error {e.code}"}, status_code=502)
    receipt = {k: s.get(k) for k in ("success", "transaction", "network", "payer", "amount", "errorReason") if k in s}
    if not s.get("success"):
        status = 202 if s.get("transaction") else 402   # broadcast but unconfirmed -> reconcile, do not re-ask
        return JSONResponse({"error": s.get("errorReason", "settle failed"), "transaction": s.get("transaction")},
                            status_code=status, headers={"PAYMENT-RESPONSE": _b64(receipt)})
    return JSONResponse(out, headers={"PAYMENT-RESPONSE": _b64(receipt)})


# ---------------------------------------------------------------- internal core
# Unpaid endpoint for the BNB Agent Studio runtime (modulusWork.ts). Protect with MODULUS_CORE_TOKEN.
core = FastAPI(title="Modulus core (internal)")


CORE_TOKEN = os.getenv("MODULUS_CORE_TOKEN", "")


@core.get("/core/verdict/{ticker}")
def core_verdict(ticker: str, request: Request):
    # The Studio runtime runs in the cloud, so this endpoint is public: require the shared bearer token,
    # otherwise the paid verdict is given away for free.
    if CORE_TOKEN and request.headers.get("authorization") != f"Bearer {CORE_TOKEN}":
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    out = _council(ticker.upper())
    return out if out is not None else JSONResponse({"error": "unknown ticker"}, status_code=404)

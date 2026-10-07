"""Paid verdicts over HTTP 402 - Modulus earns its own keep.

GET /verdict/{ticker}
  * no X-PAYMENT header -> 402 Payment Required with b402 payment requirements
    (USDT on BSC, 0.01 per verdict, payTo = the agent's own wallet)
  * with X-PAYMENT      -> POST /api/v2/b402/verify, then /api/v2/b402/settle (gas-sponsored),
    then returns the council verdict. Settlement tx hash is echoed in X-PAYMENT-RESPONSE.

Other agents (e.g. one built on BNB Agent Studio, or any Agentic Wallet user via
`baw x402-payment preview/sign`) can buy Modulus' judgment for a cent. The revenue
refills the agent's LLM / gas budget (Agent Studio `bag budget enable`).

Run:  pip install fastapi uvicorn && uvicorn modulus.server.x402_api:app --port 8402
"""
from __future__ import annotations
import base64, json, os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from ..agent import Modulus
from ..clients.binance_web3 import BinanceWeb3, Web3ApiError
from ..config import USDT_BSC

app = FastAPI(title="Modulus Council API", version="1.0")
PRICE_ATOMIC = os.getenv("MODULUS_PRICE_ATOMIC", str(10 ** 16))   # 0.01 USDT (18 decimals on BSC)
PAY_TO = os.getenv("MODULUS_WALLET_ADDRESS", "0x0000000000000000000000000000000000000000")
_m, api = None, BinanceWeb3()


def requirements(resource: str) -> dict:
    return {"x402Version": 2, "accepts": [{
        "scheme": "exact", "network": "eip155:56", "asset": USDT_BSC, "amount": PRICE_ATOMIC,
        "payTo": PAY_TO, "resource": resource, "maxTimeoutSeconds": 120,
        "description": "Modulus Council verdict on one tokenized stock (bStocks/Ondo/xStocks on BSC)",
        "mimeType": "application/json"}]}


@app.get("/health")
def health():
    return {"ok": True, "agent": "modulus", "pricing": "0.01 USDT per verdict via b402"}


@app.get("/verdict/{ticker}")
async def verdict(ticker: str, request: Request):
    global _m
    req = requirements(str(request.url))
    header = request.headers.get("X-PAYMENT")
    if not header:
        return JSONResponse(req, status_code=402)
    try:
        payload = json.loads(base64.b64decode(header))
        body = {"x402Version": 2, "paymentPayload": payload, "paymentRequirements": req["accepts"][0]}
        v = api.b402_verify(body)
        if not (v or {}).get("isValid"):
            return JSONResponse({"error": "payment invalid", "detail": v, **req}, status_code=402)
        s = api.b402_settle(body)
    except (Web3ApiError, ValueError) as e:
        return JSONResponse({"error": str(e), **req}, status_code=402)
    _m = _m or Modulus()
    res = _m.scan([ticker.upper()])
    out = res["verdicts"][0].as_dict() if res["verdicts"] else {"error": "unknown ticker"}
    resp = JSONResponse(out)
    resp.headers["X-PAYMENT-RESPONSE"] = base64.b64encode(json.dumps(s or {}).encode()).decode()
    return resp


# ---------------------------------------------------------------- internal core
# Unpaid endpoint for the co-located BNB Agent Studio runtime (sellerCore.ts).
# Studio handles ERC-8183 escrow and B402 settlement before it calls this.
from fastapi import APIRouter
core = FastAPI(title="Modulus core (internal)")


@core.get("/core/verdict/{ticker}")
def core_verdict(ticker: str):
    global _m
    _m = _m or Modulus()
    res = _m.scan([ticker.upper()])
    return res["verdicts"][0].as_dict() if res["verdicts"] else {"error": "unknown ticker"}

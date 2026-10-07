"""Keyless read-only endpoints published by the Binance Skills Hub skills
(binance-tokenized-securities-info, query-token-info, query-token-audit).
Modulus uses them so a judge can run `python -m modulus scan` with zero setup,
and as a cross-check against the signed RWA Data API.
"""
from __future__ import annotations
import json, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from ..config import BSC

WWW = "https://www.binance.com/bapi/defi"
W3 = "https://web3.binance.com/bapi/defi"
HEADERS = {"Accept-Encoding": "identity", "User-Agent": "binance-web3/1.1 (Skill) modulus/1.0"}


def _get(url: str, params: dict | None = None, retries: int = 3):
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    for a in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=20) as r:
                out = json.load(r)
            if out.get("success"):
                return out.get("data")
            raise RuntimeError(out.get("message") or out.get("code"))
        except Exception:
            if a == retries - 1:
                raise
            time.sleep(0.8 * 2 ** a)


def _post(url: str, body: dict):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={**HEADERS, "Content-Type": "application/json", "source": "agent"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("data")


def rwa_list(provider_type: int | None = None):
    """type: 1=Ondo, 2=xStocks, 3=bStocks."""
    return _get(f"{WWW}/v1/public/wallet-direct/buw/wallet/market/token/rwa/stock/detail/list/ai", {"type": provider_type}) or []


def market_status():
    return _get(f"{WWW}/v1/public/wallet-direct/buw/wallet/market/token/rwa/market/status/ai")


def asset_status(address, chain=BSC):
    return _get(f"{WWW}/v1/public/wallet-direct/buw/wallet/market/token/rwa/asset/market/status/ai",
                {"chainId": chain, "contractAddress": address})


def rwa_dynamic(address, chain=BSC):
    return _get(f"{WWW}/v2/public/wallet-direct/buw/wallet/market/token/rwa/dynamic/ai",
                {"chainId": chain, "contractAddress": address})


def rwa_meta(address, chain=BSC):
    return _get(f"{WWW}/v1/public/wallet-direct/buw/wallet/market/token/rwa/meta/ai",
                {"chainId": chain, "contractAddress": address})


def token_dynamic(address, chain=BSC):
    """On-chain flow: buy/sell volume by window, holders, top-10 %, smart-money %, KOL %, Binance avg cost."""
    return _get(f"{W3}/v4/public/wallet-direct/buw/wallet/market/token/dynamic/info/ai",
                {"chainId": chain, "contractAddress": address})


def kline(address, interval="1h", limit=300, end_time=None, chain=BSC):
    d = _get(f"{WWW}/v1/public/wallet-direct/buw/wallet/dex/market/token/kline/ai",
             {"chainId": chain, "contractAddress": address, "interval": interval, "limit": limit, "endTime": end_time})
    return (d or {}).get("klineInfos") or []


def token_audit(address, chain=BSC):
    try:
        return _post(f"{W3}/v1/public/wallet-direct/security/token/audit",
                     {"binanceChainId": chain, "contractAddress": address, "requestId": str(int(time.time()*1000))})
    except Exception as e:  # fail-closed is handled by the Sentinel
        return {"error": str(e)}


def many(fn, items, workers=8):
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(lambda x: _safe(fn, x), items))


def _safe(fn, x):
    try:
        return fn(x)
    except Exception as e:
        return {"error": str(e)}

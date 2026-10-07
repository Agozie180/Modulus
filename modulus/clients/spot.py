"""Binance Spot order-book data for bStocks (e.g. NVDABUSDT) - the deepest 24/7 venue for the token.
Public, keyless market-data mirror. Klines carry taker-buy quote volume, which is the cleanest
'who is the aggressor' signal for weekend flow."""
from __future__ import annotations
import json, time, urllib.request

BASE = "https://data-api.binance.vision/api/v3"


def klines(symbol: str, interval: str = "1h", limit: int = 120, start_ms: int | None = None):
    pair = symbol if symbol.endswith("USDT") else symbol + "USDT"
    url = f"{BASE}/klines?symbol={pair}&interval={interval}&limit={limit}" + (f"&startTime={start_ms}" if start_ms else "")
    for a in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "modulus/2.0"}), timeout=20) as r:
                k = json.load(r)
            return k if isinstance(k, list) else []
        except Exception:
            time.sleep(0.6 * 2 ** a)
    return []

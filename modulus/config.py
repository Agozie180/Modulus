"""Modulus configuration. Every knob a judge might ask about lives here."""
from __future__ import annotations
import os
from dataclasses import dataclass, field

BSC = "56"
USDT_BSC = "0x55d398326f99059fF775485246999027B3197955"
USDC_BSC = "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"
BNB_NATIVE = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"

# RWA list `type` values (from binance-agentic-wallet SKILL.md):
# 1 = Ondo (...on), 2 = xStocks (...x), 3 = bStocks (...B)
PROVIDERS = {1: "ondo", 2: "xstocks", 3: "bstock"}


@dataclass
class RiskLimits:
    max_trade_usd: float = float(os.getenv("MODULUS_MAX_TRADE_USD", "5"))       # small live amounts, per hackathon rules
    max_daily_usd: float = float(os.getenv("MODULUS_MAX_DAILY_USD", "20"))
    max_position_pct: float = 0.20          # of agent NAV per ticker
    max_slippage_pct: float = 1.0           # refuse quotes worse than this
    min_confidence: float = 0.58            # calibrated P(win) needed to act
    kelly_fraction: float = 0.25            # quarter-Kelly
    max_oracle_divergence: float = 0.15     # >15% between venues = broken feed, not an opportunity
    limit_offset_pct: float = float(os.getenv("MODULUS_LIMIT_OFFSET_PCT", "0.25"))  # weekend limit price vs reference
    min_gas_bnb: float = float(os.getenv("MODULUS_MIN_GAS_BNB", "0.002"))           # every bStock trade is an on-chain tx
    rfq_prefer_bps: float = 10.0            # take the firm RFQ price when within 10 bps of the best SWAP route


@dataclass
class Settings:
    api_key: str | None = os.getenv("BINANCE_WEB3_API_KEY")
    api_secret: str | None = os.getenv("BINANCE_WEB3_API_SECRET")
    base_url: str = os.getenv("BINANCE_WEB3_BASE_URL", "https://web3.binance.com/build")
    wallet_address: str | None = os.getenv("MODULUS_WALLET_ADDRESS")
    private_key: str | None = os.getenv("MODULUS_PRIVATE_KEY")  # only for the direct-API executor; baw needs none
    executor: str = os.getenv("MODULUS_EXECUTOR", "dryrun")      # dryrun | baw | api
    rpc_url: str = os.getenv("EVM_RPC_URL", "https://bsc-dataseed.bnbchain.org")
    ws_url: str = os.getenv("BINANCE_WEB3_WS_URL", "wss://web3-stream.binance.com/w3w/stream")
    recv_window_ms: int = int(os.getenv("BINANCE_WEB3_RECV_WINDOW", "10000"))   # <= 60000
    db_path: str = os.getenv("MODULUS_DB", "data/modulus.sqlite")
    risk: RiskLimits = field(default_factory=RiskLimits)

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key and self.api_secret)


SETTINGS = Settings()

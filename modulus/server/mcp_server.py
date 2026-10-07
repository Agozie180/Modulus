"""Modulus as an MCP server - any agent (Claude Code, Cursor, BNB Agent Studio) can ask the Council.

Tools
  modulus_verdict(ticker)     -> the council's verdict + every elder's reasoning
  modulus_scan(limit)         -> ranked verdicts across all bStocks
  modulus_twins(ticker)       -> bStock vs Ondo vs xStocks per-share prices, broken-feed flags
  modulus_calibration()       -> Brier, ECE, reliability table: how honest the confidence is
  modulus_market_clock()      -> US session state + next open/close (from the RWA layer)

Run:  pip install mcp && python -m modulus.server.mcp_server
Register in Claude Code: claude mcp add modulus -- python -m modulus.server.mcp_server
"""
from __future__ import annotations
from mcp.server.fastmcp import FastMCP
from ..agent import Modulus
from ..clients import public_bapi as pub

mcp = FastMCP("modulus")
_m: Modulus | None = None


def m() -> Modulus:
    global _m
    _m = _m or Modulus()
    return _m


@mcp.tool()
def modulus_verdict(ticker: str) -> dict:
    """Convene the Council of Elders on one tokenized stock (e.g. NVDA). Returns action, calibrated confidence, dissent and each elder's rationale."""
    res = m().scan([ticker.upper()])
    return res["verdicts"][0].as_dict() if res["verdicts"] else {"error": f"{ticker} has no bStock on BSC"}


@mcp.tool()
def modulus_scan(limit: int = 10) -> list[dict]:
    """Rank every bStock on BSC by the council's calibrated conviction."""
    return [{"symbol": v.symbol, "action": v.action, "confidence": v.confidence, "headline": v.headline}
            for v in m().scan(audit=False)["verdicts"][:limit]]


@mcp.tool()
def modulus_twins(ticker: str) -> dict:
    """Per-share price of the same company as a bStock, an Ondo token and an xStocks token on BSC."""
    from ..universe import load_universe
    a = load_universe(tickers=[ticker.upper()])
    if not a:
        return {"error": "not found"}
    return {l.provider: {"symbol": l.symbol, "per_share": l.ref_price, "address": l.address} for l in a[0].legs.values()}


@mcp.tool()
def modulus_calibration() -> dict:
    """How often Modulus is right when it says it is X% sure."""
    return m().calibration_report()


@mcp.tool()
def modulus_market_clock() -> dict:
    """US equity session for tokenized stocks: premarket/regular/postmarket/overnight/closed + next open/close."""
    return pub.market_status()


if __name__ == "__main__":
    mcp.run()

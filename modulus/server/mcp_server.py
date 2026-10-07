"""Modulus as an MCP server - any agent (Claude Code, Cursor, BNB Agent Studio) can ask the Council.

Tools
  modulus_verdict(ticker)     -> the council's verdict + every elder's reasoning
  modulus_scan(limit)         -> ranked verdicts across all bStocks
  modulus_twins(ticker)       -> bStock vs Ondo vs xStocks per-share prices, broken-feed flags
  modulus_calibration()       -> Brier, ECE, reliability table: how honest the confidence is
  modulus_market_clock()      -> US session state + next open/close (from the RWA layer)
  modulus_monday_oracle()     -> sealed-style forecast of the next US open for every bStock + out-of-sample record
  modulus_two_nights()        -> which kind of night it is and how the agent must trade right now

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


@mcp.tool()
def modulus_monday_oracle(limit: int = 15) -> dict:
    """Forecast where each real US stock opens next (P(up), expected gap) from the 24/7 bStock weekend market, plus the Oracle's out-of-sample track record."""
    from .. import oracle
    res = m().scan(audit=False)
    fc = oracle.forecast(res["moves"])
    top = dict(sorted(fc.items(), key=lambda kv: -abs(kv[1]["p_up"] - 0.5))[:limit])
    return {"regime": res["regime"], "forecasts": top, "track_record": oracle.backtest()}


@mcp.tool()
def modulus_two_nights() -> dict:
    """Dark weekend (crowd overshoots, fade), dawn (futures back), weeknight (moves informed, follow) or regular; plus the execution policy."""
    from ..clock import execution_policy
    return execution_policy()

# Modulus

**When Wall Street sleeps, five AI elders trade the gap, and they only bet what they've earned.**

Modulus is an autonomous agent for **bStocks on BNB Chain**. Every hour it convenes a Council of
five specialist elders on all 87 bStocks. They vote. A Sentinel can veto. The council's raw
enthusiasm is then **calibrated** against what actually happened before, so "60% sure" means
right about 60% of the time. Only then does it size a small trade and execute through the
**Binance Agentic Wallet**, simulating first. Other agents can buy its verdicts for $0.01 over
**x402 / B402**, through its **BNB Agent Studio** identity (ERC-8004).

> 10-second version: *Wall Street closes, but bStocks keep trading. Modulus found that the weekend
> on-chain move predicts Monday (59.8%, n=97). Five elders vote, a Sentinel can veto, and calibration
> keeps the bets honest.*

---

## Why it matters (the finding)

From 1-hour on-chain candles for all 87 bStocks (Jun 24 to Oct 7, 2026), [`research/weekend_study.py`](research/weekend_study.py):

| Weekend drift beyond the bStock market (abs) | Events | Continued into Monday's session | Avg follow PnL, pre-cost |
|---|---|---|---|
| > 0.3% | 108 | **61.1%** | +51 bps |
| > 0.5% | 97 | **59.8%** | +49 bps |
| > 1.0% | 68 | 54.4% | +77 bps |
| > 2.0% | 34 | 52.9% | +91 bps |

Fading the weekend (betting it reverts) **lost 69 bps**. The chain is early price discovery,
not noise. But per weekend the hit rate swung from **47% to 76%**, with only 4 usable weekends.
That's why Modulus caps confidence, needs a quorum and sizes with quarter-Kelly. We report the
weakness on purpose.

## The Council of Elders

| Elder | What it watches | Data |
|---|---|---|
| **The Night Watchman** (gap) | Drift since the last US close, beyond the bStock market's own move. Follows it. | Market API candles / RWA kline |
| **The Whale Watcher** (whale) | Buy vs sell flow 1h/4h/24h, smart-money and KOL holding share, Binance-wallet avg cost vs price, top-10 concentration, tracked smart-money trades | token dynamic, `baw tracker`, `baw leaderboard`, `baw signal` |
| **The Arbiter** | The same company as **bStock vs Ondo vs xStocks**, per share (price / sharesMultiplier). Flags >15% gaps as broken feeds, not free money. | RWA Data API (3 platforms) |
| **The Value Elder** | 52-week range position, P/E, ROE | RWA underlying-market / stockInfo |
| **The Sentinel** | **Veto only.** Corporate actions (dividend, split, merger), earnings limits, paused markets, stale prices, oracle sanity, token audit (fail-closed) | RWA status, `query-token-audit` |

**How the council decides** ([`council.py`](modulus/council.py))
1. Any Sentinel veto ends it: **VETO**.
2. Votes pool in log-odds, weighted by prior weight × each elder's **earned Brier skill**.
3. **Dissent** (the weight that disagrees) shrinks confidence.
4. **Quorum**: two elders must agree. No trade on one voice.
5. **Calibration** ([`calibration.py`](modulus/calibration.py)): isotonic map from raw to calibrated
   probability, shrunk toward 0.5, capped at 80%. It's seeded with the backtest and refit on every resolved verdict.
   Brier score, ECE and the reliability table are public (`python -m modulus calibration`, MCP tool `modulus_calibration`).
6. **Sizing** ([`sizing.py`](modulus/sizing.py)): quarter-Kelly on the calibrated probability × (1 − dissent),
   then $5 per trade, $20 per day and 20% per ticker caps. Agentic Wallet's own daily quota is the outer wall.

Every verdict lands in SQLite with each elder's vote. The next session scores it, and the scores
feed back into calibration and elder weights. That makes Modulus a **self-auditing** agent.

## Stack coverage

| Hackathon component | How Modulus uses it | Where |
|---|---|---|
| RWA Data API | 3-platform universe (bStocks + Ondo + xStocks), per-share price, status / next open, profile + attestations, sector tabs | `clients/binance_web3.py`, `universe.py` |
| Market API | candles, price-info, holders, top traders, top liquidity, trades, address tracker | `binance_web3.py`, Whale Watcher |
| Trading API | quote, approve (vendor-aware), swap, **RFQ** EIP-712 order submit + status for equity tokens | `executor.py` |
| Transaction API | **simulate before every trade**, gas price, broadcast with MEV protection | `executor.py` (dry-run is the default) |
| Wallet API / Address Portfolio | balances, tx detail polling, per-token PnL | `binance_web3.py`, ledger resolve |
| DeFi API | idle-USDT parking candidates between trades (investment list / deposit calldata) | `binance_web3.py` |
| b402 Payments | paid `/verdict/{ticker}`: 402 → verify → settle | `server/x402_api.py` |
| **Agentic Wallet / Wallet Skills** | `market-order` quote/swap/poll, `limit-order`, `wallet settings` quota, `tracker`, `leaderboard analyze`, `signal`, `x402-payment`, `query-token-audit`, `binance-tokenized-securities-info` | `clients/baw.py`, executor `baw` mode |
| **BNB Agent Studio** | ERC-8004 identity, ERC-8183 jobs, x402 face, self-refill budget | `agent-studio/` |
| MCP | 5 tools so any agent can ask the council | `server/mcp_server.py` |
| BNB Chain | PancakeSwap / BSC tokenized-equity liquidity via the aggregator | executor |

## Run it (60 seconds, no keys)

```bash
git clone <repo> && cd modulus
python -m modulus scan                 # live council on all 87 bStocks, read-only public data
python -m modulus explain NVDA         # every elder's reasoning
python -m modulus calibration          # Brier, ECE, reliability table
python -m pytest -q                    # 8 offline tests
```

With keys (`cp .env.example .env`):

```bash
MODULUS_EXECUTOR=dryrun python -m modulus run   # quote -> build -> Transaction API simulate
MODULUS_EXECUTOR=baw    python -m modulus run   # live, small, via Agentic Wallet (MEV on)
python -m modulus daemon                        # session-aware loop: 15 min near the open, hourly otherwise
python -m modulus.server.mcp_server             # MCP
uvicorn modulus.server.x402_api:app --port 8402 # paid verdicts
```

## Safety by design
* Simulates before it executes, and dry-run is the default. Live trades are capped at $5 each and $20 a day.
* Fail-closed: if the audit is unreachable, a feed is stale, prices diverge or the market is paused, it does nothing.
* Conditional orders are never silently turned into market orders (Agentic Wallet skill rule).
* CLI and API errors are relayed verbatim. On-chain token names are treated as untrusted (prompt-injection defense).
* Not investment advice. Tokenized securities can be halted and carry slippage and contract risk.

## Repo map
```
modulus/            agent, council, calibration, sizing, ledger, executor
modulus/elders/     gap, whale, arbiter, value, sentinel
modulus/clients/    binance_web3 (signed, all modules), public_bapi (keyless), baw (Agentic Wallet)
modulus/server/     mcp_server, x402_api (+ internal core for Agent Studio)
agent-studio/       Studio prompt + sellerCore.ts
research/           weekend_study.py, fetch_history.py, RESULTS.txt
docs/               DX report draft, demo script, submission checklist
```
Apache-2.0 licensed.

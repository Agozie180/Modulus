# The 65-Hour Market — what we learned about bStocks' weekends

Every week Wall Street is shut for **65.5 hours** (Fri 20:00 UTC → Mon 13:30 UTC). bStocks keep trading
on Binance Spot and BNB Chain. Nobody had measured what that market actually knows. We did.

**Data.** Binance Spot 1h klines for all **87 bStocks** (Jun 11 → Oct 7 2026, 144,193 candles, public
`data-api.binance.vision`), joined to the real US-listed share (Yahoo daily open/close).
**858 stock-weekends across 17 weekends.** Scripts: `fetch_spot_24x7.py`, `weekend_oracle.py`,
`oracle_deep.py`, `oracle_tradable.py`, `charts.py`. Everything reruns in under 2 minutes.

## Finding 1 — The weekend is a dark room. Liquidity drops 10×.
Weekends are **30% of the hours but 8% of the volume**. A median bStock trades **$1.6k/hour on Saturday vs
$16.4k/hour** in the US session. The book wakes up at exactly **Sun 22:00 UTC** — when CME equity futures
reopen (`docs/img/liquidity_clock.png`).

## Finding 2 — The token knows Monday's DIRECTION, not its SIZE.
At Sunday 21:00 UTC (pure crypto-only price discovery, before futures):
* market-wide: the average weekend token move called the direction of Monday's real open on **13 of 17 weekends** (corr 0.60)
* stock-specific moves > 0.5%: right direction **61.6%** (n=518), but the real gap was only **0.52×** the token move.

## Finding 3 — So the weekend crowd OVERSHOOTS, and it's tradable on spot.
Fading an idiosyncratic (market-neutral) weekend move at Sunday 21:00 UTC, P&L to Monday's open, on the token:

| weekend move | n | fade win | avg | 
|---|---|---|---|
| 0.5–1% | 230 | 56.5% | +28 bps |
| **1–2%** | 176 | **66.5%** | **+103 bps** |
| **> 2%** | 85 | **64.7%** | **+164 bps** |

13 of 14 weekends positive, 72 different tickers, symmetric for pumps (+113) and dumps (+131), holds on the
liquid subset (+137 bps). Spot-only translation: **buy the weekend panic, trim the weekend euphoria.**

## Finding 4 — Two kinds of night.
Run the same fade on **weeknights** (Mon–Thu, 03:00 UTC) and it **loses ~40 bps**. When futures, overnight ATS
venues and Asia are trading, token moves are informed; when nothing else prices US stocks, they're emotional.
Modulus' Night Watchman switches mode by clock (`modulus/clock.py`).

## Finding 5 — The discovery curve.
The token's call on Monday's direction sits at ~57% all weekend, then jumps to **68% in the hour futures reopen**,
76% by the Asia open, 88% four hours before the bell, 93% at the bell (`docs/img/discovery_curve.png`).

## Finding 6 — Monday Oracle, out-of-sample.
Forecast = 0.82 × weekend market move + 0.52 × stock-specific move. Leave-one-weekend-out (never sees the weekend it forecasts):
* all 858: Brier 0.2486 (coin-flip 0.25) — it abstains below 50 bps
* calls of a **≥ 1% gap: right 72.1% (n=262), Brier 0.2226**, 9.3% less error than "no change".

## What we got wrong (and why it matters)
Modulus v1 claimed weekend drift *continues* into Monday (59.8%, n=97) from 4 weekends of thin DEX prints.
The 17-weekend Binance Spot study overturned it. We kept the old study in the repo and changed the elder.
Calibration is the reason this agent can be wrong in public and still be trusted.

## Caveats
17 weekends is still small; Sep 11 weekend went –328 bps (real news). Costs: weekend hourly range ~22 bps,
so we trade limits only, smaller clips (size × √depth), and the Sentinel vetoes corporate-action pauses.
Not investment advice.

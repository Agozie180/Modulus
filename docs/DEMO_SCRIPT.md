# Modulus demo video (3:50, under the 4:00 limit)

Record on a **weekend** if you can (Sat or Sun before 22:00 UTC) so the dark-weekend regime is live.

**0:00-0:12 Hook.** Black screen, a clock ticking from Fri 16:00 ET. Voice: "Every week Wall Street shuts for 65 hours.
bStocks don't. Nobody had asked what that market actually knows. Modulus did."

**0:12-0:50 The finding.** The liquidity-clock heatmap, then the Two Nights bars. "On weekends only the token trades, on ten
times thinner books. The crowd gets Monday's direction right but overshoots the size about two times. Fade a 1-2% weekend move
and you win 66% by Monday's open, 13 of 14 weekends. Do the same on a weeknight and you lose, because weeknight moves are
informed. Two kinds of night."

**0:50-1:05 We were wrong first.** One slide: v1 said 'weekend drift continues, 59.8%'. Strike-through. "Seventeen weekends of
order-book data overturned it. Calibration is why you can trust an agent that's wrong in public."

**1:05-1:50 The council, live.** `python -m modulus clock` (shows dark_weekend, limit orders, smaller clips). Then
`python -m modulus explain <a ticker that moved>`: the Night Watchman says "dumped 2.4% while Wall Street was dark, fade it",
the Whale Watcher shows the aggressor flow, the Arbiter checks Ondo/xStocks, the Sentinel clears it. "Two elders agree. 66% calibrated."

**1:50-2:30 The Monday Oracle.** `python -m modulus oracle forecast`, then `oracle commit`. Send the commit tx to
WeekendOracle on BscScan. "Sealed before the bell. Nobody can edit it, not even us. Out of sample, when it calls a 1% gap it's
right 72% of the time." (Monday: cut to `oracle reveal` + `oracle grade`.)

**2:30-3:10 Live trade, small.** `MODULUS_EXECUTOR=baw python -m modulus run --tickers <ticker>`: Agentic Wallet quote, slippage
check, swap, poll to FINISHED. Cut to BscScan. "Five dollars. Limit order, because it's 3am Sunday and the book is thin."

**3:10-3:35 It earns.** Agent Studio ERC-8004 identity. `curl /verdict/NVDA` returns 402; pay with `baw x402-payment`; verdict
plus B402 settlement hash. "Other agents hire the council for a cent."

**3:35-3:50 Close.** Discovery curve on screen. "Wall Street sleeps 65 hours a week. Modulus doesn't, and it proves it on-chain."

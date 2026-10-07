# Modulus demo video (3:45, under the 4:00 limit)

**0:00-0:10 Hook.** Screen: the dashboard Page hero. Voice: "Friday, 4pm. Wall Street closes. bStocks keep trading. Modulus
is five AI elders who trade the gap and only bet what they've earned."

**0:10-0:40 The finding.** Screen: the research table. "Across 87 bStocks, weekend on-chain drift beyond the market continued
into Monday 60% of the time. Fading it lost 69 basis points. But per weekend it swung 47 to 76 percent, so confidence
must be earned, not assumed."

**0:40-1:30 The council, live.** Terminal: `python -m modulus explain DELL`. Read one verdict: Night Watchman says follow the drift,
Whale Watcher sees 68% buy-side flow, Arbiter is quiet (bStock in line with Ondo), Sentinel clears it. "2 of 2 agree, 61% calibrated."
Then show a VETO or a no-quorum HOLD: "One elder alone is not enough."

**1:30-2:00 Calibration.** `python -m modulus calibration`: reliability table, Brier, ECE. "Raw council confidence goes through
an isotonic curve fit on real outcomes. It can never claim more than 80%."

**2:00-2:50 Live trade, small.** `MODULUS_EXECUTOR=baw python -m modulus run --tickers DELL`: Agentic Wallet quote, slippage check,
swap with MEV protection, poll to FINISHED. Cut to BscScan with the tx. "Five dollars. Rules say a few dollars proves the flow."

**2:50-3:25 It earns.** Agent Studio: ERC-8004 identity on BscScan. Then `curl /verdict/NVDA`, which returns 402. Pay with
`baw x402-payment`, get the verdict, and show the B402 settlement hash. "Other agents hire the council for a cent."

**3:25-3:45 Close.** "Every API module, Agentic Wallet, Agent Studio, x402, MCP. A self-auditing agent for the hours
Wall Street sleeps. Modulus."

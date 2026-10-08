# Live mainnet trade — recorded evidence

First real trade by Modulus on **BSC mainnet (chain 56)** via the Binance Agentic Wallet (`baw`).
This is the artifact to show judges: a real, small, faithful execution — not a paper fill.

## The trade

| | |
|---|---|
| **Tx hash** | `0x9ff3ef4e5d87446aec519e6c12dde64e97a5d9890d2f3f0bbf7545b9e2ca449a` |
| Explorer | https://bsctrace.com/tx/0x9ff3ef4e5d87446aec519e6c12dde64e97a5d9890d2f3f0bbf7545b9e2ca449a |
| Order ID | `26100800001949322258` |
| Action | **BUY** SOXSB (2/2 elders, 63% calibrated confidence, 0% dissent) |
| Spent | **$1.680000 USDT** |
| Received | **0.054531550748430162 SOXSB** |
| Fill price | ~$30.81 (reference $30.86 → <0.2% slippage) |
| Status | **FINISHED** |
| Time | 2026-10-08 05:12:12 (+01:00) |
| Route | Binance Agentic Wallet market swap, MEV protection on, chain 56 |

## Balance delta (independent confirmation)

| Token | Before | After | Δ |
|---|---|---|---|
| USDT | 3.088002890681720148 | 1.408002890681720148 | −1.6800 (spent) |
| SOXSB | 0 | 0.054531550748430162 | +0.05453 (received) |
| BNB | 0.00103453 | 0.00095124000120856 | −0.00008329 (~$0.06 gas) |

## Reproduce

```bash
baw wallet status --json                 # -> CONNECTED
python -m modulus scan                   # live council over all 87 bStocks (read-only)
python -m modulus run --nav 50 --tickers SOXS   # sized buy; MODULUS_EXECUTOR=baw for live
```

## Notes for the record

- **Gas floor calibration.** The shipped `min_gas_bnb = 0.002` (~$1.54 at $769/BNB) is deliberately
  conservative; actual gas for this swap was **~$0.06** — an ~80× buffer. For a small funded demo wallet
  it is worth running with a realistic floor (`MODULUS_MIN_GAS_BNB=0.0005`). Worth calling out in the DX report.
- **Limit orders are not supported on every bStock.** At this hour the policy asks for a resting limit order,
  but the CLI returned `"Raw limit orders are not supported."` (SERVICE_ERROR, code 2) for this token, so the
  trade ran as an MEV-protected market swap. The executor **relays the CLI error verbatim and never silently
  downgrades a conditional order** — here we deliberately chose a market order. Also a DX-report item.
- This trade is the source of the on-chain link for the submission; the `WeekendOracle` commit for week
  `2026-10-09` is a separate, additional on-chain artifact.

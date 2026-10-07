# Submission checklist (submissions lock Sun 11 Oct 2026, 12:00 UTC = 13:00 Lagos)

- [ ] Register as hacker: https://forms.gle/NEmy3FxYc4f5Dua47 (you confirm you are not in a restricted region)
- [ ] Get the Web3 API key: https://web3.binance.com/en/dev-portal, then put it in `.env`
- [ ] Push this folder to a **public** GitHub repo named `modulus`
- [ ] `python -m modulus scan` works on a clean machine
- [ ] Install Agentic Wallet: `npx skills add binance/binance-skills-hub/skills/binance-web3/binance-agentic-wallet`, `npm install -g @binance/agentic-wallet@1.10.0`, then `baw auth signin --json` and `baw auth verify --qrCodeId <id> --json` (confirm in the Binance App), check `baw wallet status --json` = CONNECTED. Sessions sign out after inactivity, so re-check before the weekend.
- [ ] Also install `query-token-audit`, `binance-tokenized-securities-info`, `binance-wallet-tracker`, `binance-leaderboard`, `binance-trading-signal`
- [ ] Fund the wallet with ~$15 USDT + a little BNB for gas on **BSC mainnet**
- [ ] Run one dry-run (`MODULUS_EXECUTOR=dryrun`) and save the simulate output
- [ ] Run 1-3 live trades of ≤$5 (`MODULUS_EXECUTOR=baw`) and save the tx hashes in the README. First try one $1 bStock limit order to confirm bStocks accept limit orders, and check on Sat 10 Oct that weekend trading is open (offhours session).
- [ ] Agent Studio (bsc-testnet, BNB 48h trial): bag init moduluscouncil → wire modulusWork.ts → bag doctor → bag deploy prepare → bag deploy --provider bnb → bag deploy verify --provider bnb; save the ERC-8004 registration tx + testnet.8004scan.io link, and one ERC-8183 job (negotiate → fund → SUBMITTED → approve) tx hashes. Paid x402 only if B402 merchant onboarding is approved.
- [ ] Deploy + verify WeekendOracle on BSC testnet (chain 97) with Foundry (contracts/README.md); mainnet commit for week 20261009 between Fri 9 Oct 20:00 UTC and Sun 11 Oct 12:00 UTC.
- [ ] Do NOT claim the bStock AI PnL contest: it ran 17 Aug - 1 Sep 2026 and is over.
- [ ] Record the demo video (docs/DEMO_SCRIPT.md), ≤4 minutes, upload unlisted on YouTube
- [ ] Put the dashboard Page link in the README as the "deployed link"
- [ ] Rewrite docs/DX_REPORT_DRAFT.md in your own words, then submit it: https://forms.gle/EUQ39xf54GHjC2ys5
- [ ] Submit the project: https://forms.gle/yToDUzaDMwWnq6R6A
- [ ] Keep the repo, video and link live through judging (12-23 Oct)

# Submission checklist (submissions lock Sun 11 Oct 2026, 12:00 UTC = 13:00 Lagos)

- [ ] Register as hacker: https://forms.gle/NEmy3FxYc4f5Dua47 (you confirm you are not in a restricted region)
- [ ] Get the Web3 API key: https://web3.binance.com/en/dev-portal, then put it in `.env`
- [ ] Push this folder to a **public** GitHub repo named `modulus`
- [ ] `python -m modulus scan` works on a clean machine
- [ ] Install Agentic Wallet: `npx skills add binance/binance-skills-hub/skills/binance-web3/binance-agentic-wallet`, `npm i -g @binance/agentic-wallet`, `baw auth signin`
- [ ] Also install `query-token-audit`, `binance-tokenized-securities-info`, `binance-wallet-tracker`, `binance-leaderboard`, `binance-trading-signal`
- [ ] Fund the wallet with ~$15 USDT + a little BNB for gas on **BSC mainnet**
- [ ] Run one dry-run (`MODULUS_EXECUTOR=dryrun`) and save the simulate output
- [ ] Run 1-3 live trades of ≤$5 (`MODULUS_EXECUTOR=baw`) and save the tx hashes in the README
- [ ] Agent Studio: scaffold, deploy, record the ERC-8004 registration tx, and do one paid x402 call
- [ ] Record the demo video (docs/DEMO_SCRIPT.md), ≤4 minutes, upload unlisted on YouTube
- [ ] Put the dashboard Page link in the README as the "deployed link"
- [ ] Rewrite docs/DX_REPORT_DRAFT.md in your own words, then submit it: https://forms.gle/EUQ39xf54GHjC2ys5
- [ ] Submit the project: https://forms.gle/yToDUzaDMwWnq6R6A
- [ ] Keep the repo, video and link live through judging (12-23 Oct)

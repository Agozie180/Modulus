# DX Report — Findings Dossier (RAW MATERIAL — DO NOT SUBMIT AS-IS)

> ⚠️ **This file is scratch notes, not the report.** The hackathon's Developer Experience Report is **25% of the score** and the organizers **reject AI-generated or perfunctory reports**. Use the bullets below as a checklist of real things we hit, then **write the report in your own voice, from your own experience**, in `docs/DX_REPORT_DRAFT.md`. Delete anything you didn't personally verify, and fill the `[YOU FILL]` timing/experience items yourself.
>
> `[VERIFY]` = we believe this from the docs but it needs a live API key / live `baw` to confirm. Do **not** state a `[VERIFY]` item as fact in the report — either confirm it first, or frame it as "the docs were unclear on X."

---

## 1. Onboarding (fill timings yourself)
- Dev portal + API key: https://web3.binance.com/en/dev-portal . `[YOU FILL]` how long from signup → working key.
- Official SDKs exist (JS `@binance-web3/wallet`, Python `binance-web3-wallet`, Java) — we hand-rolled a stdlib client instead; note whether you'd have preferred the SDK.
- **Region friction (real):** the public Binance Spot REST host `api.binance.com` is geo-blocked in some locations; we had to pull 24/7 spot klines from the `data-api.binance.vision` mirror. `[YOU FILL]` whether you hit this and how you worked around it.

## 2. Documentation issues (genuine, high-value feedback)
- The `llms.txt` / `llms-full.txt` docs are great for the **Trading, DeFi-flow, B402, Auth and Rate-limit** sections, but the **RWA, Market, Wallet and Transaction** sections are **description-only** — endpoint path + one-line purpose, **no request params and no response field schemas**. Those live only in the interactive HTML reference.
- Concretely missing from the text docs: the per-share multiplier field name (we assume `sharesMultiplier`), RWA market-status / next-open field names, attestation fields, and `ROE`. `[VERIFY]` the real field names against a live response.
- RFQ order status: only `FILLED` / `FAILED` are enumerated verbatim; `EXPIRED` / `CANCELLED` / `PENDING` are implied but never listed.
- B402 error-code table and the exact x402 header set are referenced but not spelled out in one place.
- Suggestion: publish the RWA/Market/Wallet/Transaction response schemas in `llms-full.txt` so an agent can integrate without opening the HTML console.

## 3. API pitfalls we hit (the stuff that bites)
- **Business errors come back as HTTP 200** with a non-zero `code` in the envelope (`{code,msg,data,success}`). You must branch on `code`, not the HTTP status, or you'll treat a failed call as success. (We handle this and test it.)
- **Request signing:** the signed `requestPath` includes the `/build` prefix; timestamp is **ISO-8601 with ms**; `preHash = timestamp + method + requestPath + body`, HMAC-SHA256 → base64. Easy to get subtly wrong.
- **RFQ submit `quoteId` is NOT the `/quote` route id** — it's `rfq.orderId` from the quote's `rfq` block, with a fresh `requestId` UUID per order (reused on retry). `[VERIFY]` end-to-end with a key — this is the single easiest RFQ mistake to make.
- `priceImpactProtectionPercent` defaults to **90** (not 100); set it to 100 to disable; a breach returns `40463`.
- Quote TTL is ~**30 s** → `40401 QUOTE_EXPIRED`; you must re-quote after an approve.
- MEV protection flag on broadcast is exactly `enableMevProtection` (boolean, EVM only).
- Per-endpoint rate limit is **5 RPS** — a naive "scan all 87 bStocks" loop needs throttling.

## 4. AI-stack feedback (Agentic Wallet / Agent Studio — the special-prize sections)
- Install is **two things**, and it's easy to confuse them: the `baw` CLI (`npm install -g @binance/agentic-wallet@1.10.0`) **and** the skill (`npx skills add binance/binance-skills-hub/skills/binance-web3/binance-agentic-wallet`). Required CLI version 1.10.0, skill 1.12.0.
- **`tracker` / `leaderboard` / `signal` are separate wallet-skills, not `baw` subcommands** (`binance-wallet-tracker`, `binance-leaderboard`, `binance-trading-signal`). The core `baw` verbs are auth/wallet/approvals/market-order/limit-order/contract-call/sign-message/prediction/x402-payment/defi/skill-check/cli-check. We initially called them as `baw tracker …`; flag this naming as a documentation gap. `[VERIFY]` the exact invocation once the skills are installed.
- **Guardrail nuance we got wrong at first:** an eligible bStock earns a **security pre-check exemption** (it may skip `query-token-audit`) — it does **NOT** bypass the wallet `dailyLimit`. There are also *separate* 24h quotas (`x402DailyLimit`, `defiDailyLimit`, `devMode.dailyLimit`). Worth calling out as non-obvious.
- A `market-order` `orderId` / `limit-order` `strategyId` with `success:true` means **submitted, not filled** — you must poll `…list` to a terminal state. x402 signatures are single-use and ~30 s. `[YOU FILL]` your real polling experience.
- Studio: the generated scaffold is `studio.toml` + `src/sellerCore.ts` (the `runWork` hook) + `src/signing.ts` (pricing/signing stay out of the LLM). `[VERIFY]` the exact main-entry filename your `bag init` generates (docs mention `main.ts`/`mcpMain.ts`/`dualMain.ts`); our README says `unifiedMain.ts` — reconcile with what ships.
- `[VERIFY]` the `bag` subcommands our docs use (`erc8183 settle`, `x402 sell init`, `budget enable`, `audit ls`) against the installed `bag` — some may differ from the published CLI README.
- Binance's own Web3 **MCP server is "coming soon," not live** — so shipping our own MCP server is a real gap-filler, not redundant. Good thing to say out loud.

## 5. Tokenized-stock specifics (the section judges care most about)
- **1 token ≠ 1 share — CONFIRMED with a live key.** `GET /api/v1/dex/market/rwa/price` returns BOTH prices for a token: for SOXSB, `tokenPrice: "30.63000000"` and `referencePrice: "30.356"`, and `tokenInfo.sharesMultiplier: "1.009026219854107205"`. **30.63 ÷ 1.009026 = 30.356** exactly. So the per-share divisor is confirmed to be `sharesMultiplier` (previously only inferred — the text docs never named the field). Our Arbiter compares bStock vs Ondo vs xStocks **per share** and flags >15% gaps as broken feeds.
- Symbol conventions: bStock = `type=3`, suffix `…B`; Ondo = `type=1`, suffix `…on`; xStocks = `type=2`, suffix `…x`.
- **Weekend liquidity (our whole thesis):** on weekends only the token trades, on ~10× thinner books (Sat ~$1.6k vs ~$16.4k per bStock-hour). `[YOU FILL]` the real slippage you saw on your live ≤$5 trades — this is the money quote for the report. (Our one live trade filled at $30.81 vs $30.86 reference — <0.2%.)
- Market-closed is signalled by trading error codes, not a boolean: `40369 BSTOCK_INVALID_TRADING_TIME`, `40367 ONDO_MARKET_STATE_NOT_TRADABLE`. We map `40369 → DEFERRED`.
- **RFQ route not observed on our pairs — CORRECTED.** With a live key, both `USDT→SOXSB` and `USDT→NVDAB` quotes returned `executionMode: "SWAP"`, `vendorName: "LiquidMesh"`, and an **empty `rfq` block** — no RFQ route was offered. So the `quoteId` (route id) vs `rfq.orderId` distinction is **conditional on `executionMode == "RFQ"`**; our code handles both, but we could not reproduce an RFQ quote to test that branch live. Worth stating honestly in the report.
- **`--tickers` accepts the bStock symbol too.** We hit a real papercut: the README shows `python -m modulus run --tickers IBMB`, but the universe is keyed on the base ticker (`IBM`), so `IBMB` matched nothing and the run silently did nothing. Fixed to accept either form.
- `[YOU FILL]` off-hours behavior you observed: did quotes keep returning off-hours? did limit orders rest correctly in thin books? (We found limit orders were **unsupported for our token** — see §4/AI-stack.)

## 5b. Endpoints confirmed live with a key (all returned 200 + data)
`rwa/price` · `rwa/tokens` · `aggregator/quote` · `portfolio/overview` · `balance/all-token-balances-by-address` · `defi/data/investment/list` (**58 opportunities**) · `market/candles`. So the signed-API path (the `/build` prefix + HMAC signing) works end to end — a good thing to state in the report, since getting the signing wrong is the usual failure mode.

## 6. Redesign suggestions / requested capabilities (end the report strong)
- Publish RWA/Market/Wallet/Transaction **response schemas** in the text docs.
- Fully enumerate the **RFQ status** state machine and the **`baw` exit codes**.
- Clarify the **`dailyLimit` vs pre-check-exemption** distinction for eligible bStocks in one place.
- A documented **"park idle stablecoin" discovery** (which `investment/list` entries are safe for an agent between trades) would save every trading-agent team the same research — right now it's an app-layer guess.
- Document the **WebSocket auth-token** flow (`/market/wss/auth/token` → `wss://web3-stream…`) with an agent example; we left streaming out because it wasn't worth reverse-engineering under deadline.

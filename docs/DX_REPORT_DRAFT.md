# Developer Experience Report: Modulus (DRAFT, rewrite in your own words)

> The organisers reject AI-generated or perfunctory reports, and this is 25% of the score.
> Use this as a **notebook of verified facts**: every item below was seen while building Modulus on
> 7 Oct 2026. Re-check each `[VERIFY]` item with your own API key, add your own timings and
> frustrations in your own voice, and delete anything you did not personally hit.

## 1. Onboarding
- [YOU FILL] Time from opening the docs to the first successful signed call: ___ min. Time to get the API key approved: ___.
- The **Authentication page renders empty without JavaScript** (a static fetch of
  `https://web3.binance.com/en/dev-docs/authentication` returns only the footer). It's the one page every
  integrator needs first.
- The exact pre-hash (timestamp + METHOD + requestPath incl. `/build` + query/body, HMAC-SHA256, Base64)
  is easiest to piece together from **Trading API › Integration Flow › Common Pitfalls (40102)**, not from one
  canonical example. `[VERIFY]` that your first signed call matched it, and note how many tries it took.
- "Feed the docs to your agent": `llms.txt` / `llms-full.txt` and the `.md` page variants returned **0 bytes to plain
  `curl`** from a server environment (they did load via a browser-like fetcher). That's the exact path an agent uses.

## 2. Documentation issues (page › section › what is wrong)
1. **RWA Data › Get RWA Token Price › `referencePrice`** says: "A per-share converted price derived from the
   on-chain token price, not an official quote from the traditional stock market." The hackathon brief pitches the
   "on-chain vs reference price" gap, but that field is derived from the on-chain price itself, so the gap is circular. The real
   underlying (`stockInfo.price` in the skill's dynamic endpoint) is `null` outside US hours, exactly when the gap matters.
2. **RWA Data › `platformId` enum** lists only `ondo` and `bstock`. xStocks is allowed by the track rules, and the
   skill list endpoint returns **130 xStocks tokens on BSC** (`type=2`), but the REST API can't filter for them.
3. **Two meanings of "type"**: the skill list uses `type` 1=Ondo, 2=xStocks, 3=bStock, while REST `assetType` uses
   1=Stock, 2=Pre-IPO, 3=ETF. Same numbers, different meanings, one bug waiting to happen.
4. **Skills Hub › `binance-tokenized-securities-info` SKILL.md** still says Ondo is "currently the only supported tokenized
   stock provider" (`type=1`), while the same endpoint returns **87 bStocks** with `type=3`. The `binance-agentic-wallet`
   SKILL.md even warns that older versions only know `type=1`.
5. **RWA dynamic (v2) for bStocks**: `statusInfo.marketStatus`, `tokenInfo.totalHolders`, `marketCap` and `circulatingSupply`
   came back `null` for NVDAB. `tokenInfo.volume24h` = `20601044893` (US stock volume), while on-chain buy+sell over 24h for
   the same token was about **$5.96M**. The skill doc calls this field "misleading". It should be renamed, not footnoted.
6. **Market status (overnight session)** returned `openState: true` with `nextClose` (07:55 UTC) *earlier* than
   `nextOpen` (08:01 UTC), plus an undocumented `offhours` object.
7. **Trading API › RFQ mode**: `/order/submit.quoteId` must be `rfq.orderId`, not the `/quote` route `quoteId`. The doc
   does warn about it, but the field name invites the mistake. Rename to `rfqOrderId`. `[VERIFY]` whether you hit it.

## 3. API pitfalls
- **Token audit doesn't cover tokenized stocks**: `security/token/audit` for NVDAB returned `isSupported: false`,
  `riskLevel: -1`. The Agentic Wallet security policy makes this audit a mandatory pre-swap step, so every bStock trade falls into
  "audit unavailable". Modulus treats `isSupported:false` as neutral and keeps other Sentinel checks fail-closed.
- **Kline history**: paging 1h candles with `endTime` stopped returning older data after the 2nd page (599 candles per token),
  so a longer backtest isn't possible from this endpoint. `[VERIFY]` with the signed `/market/candles`.
- `[VERIFY]` quote latency, how often `quoteId` expired (~30 s), and the RFQ fill time on your live demo trades. Write the numbers.

## 4. AI stack feedback (Agentic Wallet / Wallet Skills / CLI)
- [YOU FILL] Install + `baw auth signin` experience, time to the first quote.
- What worked: the skill's routing table, `--json` on every command, and the rule "an orderId is NOT a completed swap, poll to
  FINISHED/FAILED", which saved us from false success messages.
- Missing: a non-interactive mode for agents that run unattended (confirmation is designed around a chat human). Per-strategy
  spend caps under the global daily quota. A `tracker` filter by token address, to watch whales of one bStock.
- `[VERIFY]` whether `limit-order` works on bStocks (the skill mentions `Ondo-related tokens cannot be traded` for limits).

## 5. Tokenized-stock specifics (measured)
- **bStock vs Ondo, same company, per share**: median gap **7.2 bps**, p90 **24.7 bps** across 72 overlapping tickers. That's tight.
- **bStock vs xStocks on BSC**: median gap **775 bps**. **9 of 27** overlapping tickers were more than 15% apart (NFLX, IBM, CRWD,
  TQQQ, GME, MRVL, TSM, META, MSTR). Most likely unadjusted splits or multipliers, or stale BSC pools. Any naive cross-protocol arb bot
  would buy a broken feed.
- **Outside market hours**: the market-neutral weekend drift of bStocks continued into Monday's session **59.8%** of the time
  (n=97, 4 weekends, +49 bps avg pre-cost). Fading it lost 69 bps.
- [YOU FILL] Liquidity and slippage you saw on your live trades (size, quoted vs filled, MEV on/off).

## 6. Redesign suggestions
- One "first call" page: a copy-paste signed request in curl, Python and JS that works with your key in the URL bar.
- A keyless sandbox tier for RWA Data and Market (the public skill endpoints already prove it can work).
- A real `underlyingLastPrice` + `underlyingPriceTime`, kept separate from the derived `referencePrice`.

## 7. Requested capabilities
- An earnings / corporate-action **calendar** endpoint with dates (tab 3 "Upcoming Earnings" has no dates).
- A WebSocket for RWA status changes (paused, limited, open) and next-open events.
- Historical reference price series, and kline history beyond ~25 days.
- Token audit coverage for RWA issuers (bStocks, Ondo, xStocks).
- [CORRECTED] A Python SDK (`pip install binance-web3-wallet`) and a Postman pre-request signing script do exist (SDKs & Tools, Authentication), but every docs page renders empty to curl/static fetchers (AWS WAF challenge, HTTP 202, 0 bytes). We only found them inside llms-full.txt. Make the .md pages fetchable.

## Added during the 24/7 deep dive [VERIFY + rewrite in your own words]
- `api.binance.com/api/v3/klines` refused our server ("Service unavailable from a restricted location"), but the public
  market-data mirror `data-api.binance.vision` served the same bStock klines (e.g. `NVDABUSDT`). Nothing in the bStock or
  Web3 docs points builders to the mirror; we found it by trial.
- The RWA list carries a `cs` field (e.g. `MUBUSDT`): the Binance Spot pair for the token. It is undocumented in the skill,
  and it is the key that joins on-chain data to the deepest 24/7 order book. Please document it.
- The market-status endpoint returns an `offhours` object (Sat 00:06 UTC to Sun 23:55 UTC in our sample) that the skill's
  field table does not describe.
- The on-chain DEX kline endpoint omits hours with no trades, so a naive weekend study on it looks like 4 usable weekends;
  the Spot order book gave us 17. Our first conclusion (weekend drift continues) flipped once we had the deeper data.

## Found while reading every docs page end to end [VERIFY + rewrite]
- B402 returns success as code "000000000" while every other module uses 0, and B402 bodies need an outer {"body": ...} envelope. Easy to miss; our first client rejected successful settlements.
- Transaction API simulate takes evmTx{from,to,value,data}; we first sent a different shape and got 40001 on every dry run.
- bStock quotes return both a SWAP route and an RFQ route; the RFQ typedDataToSign is documented as "hex string (or JSON-encoded string)" with a 0x1901 example. One canonical format would help.
- The /swap rfq object: one page lists orderId, the OpenAPI schema does not.
- quoteId lives 30 s, but an ERC-20 approval confirmation can take longer, so the docs should say "re-quote after approving".
- Agentic Wallet: per the campaign rules an eligible bStock only skips the `query-token-audit` pre-check — whether it also skips the `dailyLimit` is UNVERIFIED (we had assumed it did), `[VERIFY]` with a live key. Whether bStocks accept limit orders, and the baw exit codes, are not documented either.
- Studio: the generated sellerCore.ts must export SellerCore/RunWork; the integration seam (RunWork) is not described for non-LLM work.
- Solidity: we named a mapping `weeks` (a reserved time unit). Our fault, but a lint step in Studio templates would catch it.

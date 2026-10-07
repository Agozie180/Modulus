# Modulus on BNB Agent Studio

Modulus runs as a persistent on-chain agent with its own **ERC-8004 identity**, an **ERC-8183**
task interface, and an **x402/B402** paid face. Other agents hire the Council for a verdict;
the fees keep Modulus' LLM and gas budget topped up (self-funding).

## 1. Scaffold (one prompt, inside Claude Code or Cursor)

```bash
npm install --global @bnbagent/studio-cli
bag skills install          # installs the /bnbagent-studio skill into your IDE
```

Prompt to paste into your IDE:

> Create a seller agent called **modulus-council** on **bsc-testnet** (switch to bsc-mainnet for the demo),
> wallet `evm-local`, LLM Pieverse `auto/free`, commerce rails **ERC-8183 and B402**, public faces
> **A2A, MCP and X402**, deliverable storage **IPFS**. It sells one service: "Council verdict on a
> tokenized stock" priced at `price_usd = "0.01"`. The input is a stock ticker (e.g. NVDA). The work is
> done by calling `GET ${MODULUS_CORE_URL}/core/verdict/{ticker}` and returning the JSON.

## 2. Replace the generated `app/agent/src/sellerCore.ts`

Use [`sellerCore.ts`](sellerCore.ts) from this folder. It is the only file you edit; signing stays in
Studio's fixed `signing.ts` (no LLM ever signs).

## 3. Run the Python council next to it

```bash
pip install -r requirements.txt
uvicorn modulus.server.x402_api:core --port 8402   # exposes /core/verdict/{ticker} (internal, unpaid)
export MODULUS_CORE_URL=http://127.0.0.1:8402
```

## 4. Deploy and verify

> Deploy my agent to the BNB managed trial and verify it's live.

Studio registers the ERC-8004 identity, brings the ERC-8183 `negotiate` / `notify_funded` rail up,
and serves `/x402`. Turn on self-refill: `bag budget enable` (balance floor, refill amount, daily cap).

## What to show judges

* the ERC-8004 registration tx on BscScan / BSCTrace
* one paid `/x402` call settling through B402 (tx hash in `X-PAYMENT-RESPONSE`)
* one ERC-8183 job: negotiate -> fund -> deliverable (IPFS CID of the verdict) -> approve
* the agent's own wallet balance rising by the fee

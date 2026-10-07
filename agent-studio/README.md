# Modulus on BNB Agent Studio

Modulus runs as a BNB Agent Studio **seller**: its own **ERC-8004 identity** on BSC, an **ERC-8183** escrowed job
interface (`negotiate` / `notify_funded`) and an **X402** face settled through **B402**. Other agents hire the
Council of Elders for a calibrated verdict on a tokenized stock; the fee lands in the agent's own wallet.

Docs: https://docs.bnbchain.org/developer-kit/bnbchain-studio/ (Quickstart, Deployment). Studio CLI 0.0.14.
Requirements: Node.js ≥ 22, Corepack + pnpm 10, Bun ≥ 1.3, Claude Code or Cursor.

## 1. Install Studio and scaffold (BSC testnet)

```bash
npm install --global @bnbagent/studio-cli
bag skills install            # installs the /bnbagent-studio skill; reload your IDE
```

Prompt to paste into Claude Code / Cursor:

> /bnbagent-studio Create a BNB Chain seller agent named **moduluscouncil** on **bsc-testnet**, wallet `evm-local`
> (a fresh throwaway wallet), default LLM (Pieverse `auto/free`), commerce rails **ERC-8183 and B402**, public faces
> **A2A, MCP and X402**, prepared for the **48-hour BNB testnet trial**. Seller price `price_usd = "0.01"`.
> It sells one service: "Council verdict on a tokenized stock (bStocks / Ondo / xStocks on BSC)". The work is done by
> `app/agent/src/modulusWork.ts`, which I will add.

(Names must match `^[A-Za-z][A-Za-z0-9]{0,22}$` — no hyphens. The managed trial is always bsc-testnet.)

## 2. Add the Modulus work hook (do NOT replace the generated sellerCore.ts)

```bash
cp agent-studio/modulusWork.ts <workspace>/app/agent/src/modulusWork.ts
```
Then in `app/agent/src/unifiedMain.ts` and `app/agent/src/mcpMain.ts`:
```ts
import { buildModulusRunWork } from "./modulusWork.js";
// const runWork = buildRunWork();           // generated default (generic LLM passthrough)
const runWork = buildModulusRunWork();       // Modulus council verdict
```
Set the price in `app/agent/studio.toml`:
```toml
[payments.seller]
price_usd = "0.01"
assets = ["TEST_U"]
```
Pricing and all signing stay in Studio's fixed code (`signing.ts`); the LLM never prices or signs.

## 3. Run the Python council where the cloud runtime can reach it

```bash
pip install -r requirements.txt
export MODULUS_CORE_TOKEN=<long random string>
uvicorn modulus.server.x402_api:core --host 0.0.0.0 --port 8403   # /core/verdict/{ticker}, bearer-protected
```
Expose it over HTTPS (tunnel or VPS) and put that URL in `CORE` in `modulusWork.ts` (the deployed runtime does not
read `.env.local`; `127.0.0.1` is not your laptop once deployed).

## 4. Check, run locally, deploy, verify

```bash
bag doctor
bag dev                                   # A2A :9000, MCP http://localhost:8000/mcp, X402 /x402
bag deploy prepare
bag deploy --provider bnb                 # 48h managed testnet trial; clock starts on first success
bag deploy verify --provider bnb          # reconciles the ERC-8004 identity with the live endpoint
bag erc8004 show
bag deploy status --provider bnb
```
ERC-8004 registration is gas-sponsored (MegaFuel). Testnet tBNB: https://www.bnbchain.org/en/testnet-faucet ·
test U: https://united-coin-u.github.io/u-faucet/

## 5. Earn

* ERC-8183: a buyer calls `negotiate` (task_description `ticker=NVDA`), funds the job, sends `notify_funded`; Modulus
  verifies on-chain, submits the verdict, and the buyer approves. Operator settle: `bag erc8183 settle <jobId>`.
* X402: `GET /x402?prompt=NVDA` → 402 challenge → pay → verdict (paid mode needs B402 merchant onboarding:
  `bag x402 sell init`, `bag x402 sell status`).
* `bag audit ls` lists every on-chain action. `bag budget enable` (mainnet) renews LLM credit from the wallet.

## What to show judges (record these — the trial expires after 48h)

* ERC-8004 registration tx on testnet.bscscan.com and the agent page on https://testnet.8004scan.io/
* one ERC-8183 job: negotiate → createJob/fund → SUBMITTED (deliverable URL) → approve, with tx hashes
* if B402 is live: one paid `/x402` call and its `X-PAYMENT-RESPONSE` receipt
* the agent wallet balance rising by the fee

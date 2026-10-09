# Modulus on BNB Agent Studio — deployed & verified

Modulus runs as a BNB Agent Studio **seller agent** on the managed platform. Other agents hire the
Council of Elders for a calibrated verdict on a tokenized stock; the ERC-8183 commerce rail signs the
price and the Modulus Python core (reached over a public tunnel) produces the verdict.

## Live deployment (recorded 2026-10-09)

| | |
|---|---|
| Runtime / agent id | `01M4F7C2ZWWBQ10DNRSFCNMT00` |
| Status | **running** — BNB Chain managed trial |
| Agent card (public) | https://bnbagent-api.bnbchain.world/v1/rt/01M4F7C2ZWWBQ10DNRSFCNMT00/.well-known/agent-card.json |
| A2A invoke (JSON-RPC) | https://bnbagent-api.bnbchain.world/v1/rt/01M4F7C2ZWWBQ10DNRSFCNMT00/a2a |
| Agent wallet (signer) | `0xDA53Dc3b16A14076Fc2523c23f2d91F7ea30c2f8` (throwaway testnet wallet) |
| ERC-8004 identity | agent **#2581** on registry `0x8004A818BFB912233c491871b3d84c89A494BD9e` (BSC testnet, chain 97), relayed gaslessly by the operator via `bag deploy verify` |
| Commerce rails | ERC-8183 (negotiate / notify_funded) + B402 face |
| LLM | Pieverse `auto/free` (zero-deposit) — but delivery work is the Modulus council, not the LLM |
| Skills | `negotiate`, `notify_funded` over A2A |

Trial expires **2026-10-11T02:20Z** (managed trials last 48h). Artifacts below are the durable proof;
the live endpoint is only up during the trial window.

## Verified end-to-end: a signed ERC-8183 quote

Called `negotiate` for `ticker=NVDA` over OAuth2 + A2A (`docs/artifacts/agent_negotiate.json`). The
deployed agent returned an **accepted, signed** quote:

```json
{
  "response": {
    "accepted": true,
    "terms": { "deliverables": "Council verdict on NVDA",
               "price": "10000000000000000",
               "currency": "0xc70B8741B8B07A6d61E54fd4B20f22Fa648E5565" },
    "estimated_completion_seconds": 600,
    "quote_expires_at": 1791513576
  },
  "negotiation_hash": "0xca425125fb58ce3a54ee50560d8cc85ba441fd66bdc00207181d1af6486db3e3",
  "provider_sig": "0x8dd0207a7425f4d6544a283c313cc7f1c44439aab41a58cdb911a5ccb844622673e4cdc66f26a7d4690234ee4765ba33b291d543e4b64be9ab6f07549331ad1f1c",
  "chain_id": 97,
  "verifying_contract": "0xa206c0517B6371C6638CD9e4a42Cc9f02A33B0DE"
}
```

- **price** `10000000000000000` = 0.01 testnet U (18 decimals).
- **provider_sig** is an EIP-191 signature from the agent wallet over the negotiation hash — a buyer anchors
  this on-chain via ERC-8183 `createJob → registerJob → setBudget → fund`, then calls `notify_funded`, and the
  agent delivers the Modulus verdict on-chain. Pricing + signing are fixed code (`signing.ts`), never the LLM.

## How a buyer calls it

1. OAuth2 client-credentials token at `https://bnbagent-api.bnbchain.world/v1/oauth/token`
   (scope `invoke:01M4F7C2ZWWBQ10DNRSFCNMT00`).
2. `negotiate` (data part) → signed quote (above).
3. Fund the job on-chain with U, then `notify_funded {job_id}` → the agent fetches the Council verdict from the
   Modulus core and submits the deliverable on-chain; the buyer polls the chain for SUBMITTED.

## The work hook

`app/agent/src/modulusWork.ts` implements Studio's `RunWork` seam: it extracts the ticker and calls the Modulus
Python core (`uvicorn modulus.server.x402_api:core`) at a bearer-protected `/core/verdict/{ticker}`. In this
deployment the core is served from the dev machine over a Cloudflare quick tunnel; for a durable deployment it
should move to an always-on host.

## Honest limitations

- **x402 paid rail is dormant** — the public x402 route returns 404 because PAID mode needs four B402 merchant
  credentials (a separate Binance developer-account application for this exact wallet). ERC-8183 (the rail shown
  above) is fully live; x402 would need that merchant onboarding.
- **ERC-8004 on-chain identity: registered** — agent **#2581** on the BSC-testnet registry
  `0x8004A818BFB912233c491871b3d84c89A494BD9e`, relayed **gaslessly** by the operator via
  `bag deploy verify` (no gas spent from the wallet). The agent wallet also holds 0.11 tBNB + 5 U for
  ERC-8183 settlement.
- **The core runs behind a dev tunnel** — it is up while the demo machine + tunnel are running, not 24/7.

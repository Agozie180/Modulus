// modulusWork.ts - Modulus' work hook for a BNB Agent Studio seller (copy to app/agent/src/modulusWork.ts).
//
// Studio's real seam is the `RunWork` hook: (prompt, { sessionId, abortSignal }) => Promise<string>.
// It is called (a) by ERC-8183 delivery after the funded job is verified on-chain (sessionId = jobId),
// and (b) by the X402 face after B402 has settled the payment (sessionId = "b402").
// Pricing lives in studio.toml [payments.seller].price_usd and signing stays in signing.ts - never here.
//
// Wire it in two generated files (one line each):
//   src/unifiedMain.ts : const runWork = buildRunWork();            ->  const runWork = buildModulusRunWork();
//   src/mcpMain.ts     : const runWork = opts.runWork ?? buildRunWork(); and the later `const runWork = buildRunWork();`
//                        ->  buildModulusRunWork()
//   plus in both:        import { buildModulusRunWork } from "./modulusWork.js";
//
// Buyers ask for a ticker in any of these forms:
//   x402  : GET /x402?prompt=NVDA   or   POST /x402 {"prompt":"NVDA"}
//   8183  : negotiate {"task_description":"ticker=NVDA", ...}  (or {"ticker":"NVDA"} inside task/terms)

import type { RunWork } from "./sellerCore.js";

// The deployed runtime runs in the cloud (BNB managed trial = operator's AWS), so this must be a PUBLIC
// HTTPS URL of `uvicorn modulus.server.x402_api:core`, never 127.0.0.1. The runtime does not read
// .env.local, so the constant below is the value that actually ships; the env var only helps `bag dev`.
const CORE = (process.env.MODULUS_CORE_URL ?? "https://REPLACE-ME.example.com").replace(/\/+$/, "");
const CORE_TOKEN = process.env.MODULUS_CORE_TOKEN ?? ""; // optional shared secret checked by the core
const TICKER = /^[A-Z]{1,6}(?:\.[A-Z]{1,2})?$/;          // NVDA, BRK.B
const CORE_TIMEOUT_MS = 90_000;

// Fail loud instead of silently shipping a dead URL: the placeholder below is NOT a real host, and a
// deployment that never set MODULUS_CORE_URL would otherwise answer every paid call with a 404/DNS
// error. Bake the real public HTTPS origin in above (or set the env var) before deploy.
function coreBase(): string {
  if (!CORE || CORE.includes("REPLACE-ME")) {
    throw new Error(
      "modulusWork: MODULUS_CORE_URL is unset (still the REPLACE-ME placeholder). " +
        "Set it to the deployed public HTTPS origin of `uvicorn modulus.server.x402_api:core` " +
        "(e.g. https://<your-core-host>) before deploy, or via MODULUS_CORE_URL in `bag dev`.",
    );
  }
  return CORE;
}

export function extractTicker(prompt: string): string | null {
  const raw = String(prompt ?? "").trim();
  const bare = raw.toUpperCase();
  if (TICKER.test(bare)) return bare;
  try {
    const j = JSON.parse(raw) as unknown;
    if (j && typeof j === "object" && "ticker" in j) {
      const t = String((j as { ticker: unknown }).ticker).trim().toUpperCase();
      if (TICKER.test(t)) return t;
    }
  } catch {
    /* not JSON */
  }
  // "ticker=NVDA", "ticker: NVDA", {"ticker":"NVDA"} and its JSON-escaped form inside the 8183 JOB CONTEXT
  const m = raw.match(/ticker\\?"?\s*[:=]\s*\\?"?([A-Za-z]{1,6}(?:\.[A-Za-z]{1,2})?)/i);
  if (m) {
    const t = m[1].toUpperCase();
    if (TICKER.test(t)) return t;
  }
  return null;
}

export function buildModulusRunWork(): RunWork {
  return async (prompt, { sessionId, abortSignal }) => {
    const ticker = extractTicker(prompt);
    if (!ticker) {
      const msg = 'no ticker found; send "NVDA", {"ticker":"NVDA"} or "ticker=NVDA"';
      // x402 has ALREADY settled before work runs and Studio has no automatic refund, so answer instead of
      // throwing. For ERC-8183 we throw: the job stays FUNDED with no deliverable and the buyer keeps recourse.
      if (sessionId === "b402") return JSON.stringify({ agent: "modulus", error: msg });
      throw new Error(msg);
    }
    const core = coreBase();
    const timeout = AbortSignal.timeout(CORE_TIMEOUT_MS);
    const signal = abortSignal ? AbortSignal.any([abortSignal, timeout]) : timeout;
    const r = await fetch(`${core}/core/verdict/${encodeURIComponent(ticker)}`, {
      signal,
      headers: CORE_TOKEN ? { authorization: `Bearer ${CORE_TOKEN}` } : {},
    });
    if (!r.ok) throw new Error(`council unavailable: HTTP ${r.status}`);
    const verdict = (await r.json()) as Record<string, unknown>;
    return JSON.stringify(
      {
        agent: "modulus",
        service: "modulus-council-verdict",
        ticker,
        verdict,
        disclaimer: "Research output, not investment advice. Calibrated on Jun-Oct 2026 bStock data.",
        servedAt: new Date().toISOString(),
        session: sessionId,
      },
      null,
      2,
    );
  };
}

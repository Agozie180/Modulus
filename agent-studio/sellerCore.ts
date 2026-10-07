// sellerCore.ts - the only file you own in the Studio scaffold.
// Modulus sells one thing: the Council of Elders' calibrated verdict on a tokenized stock.
// Signing, quoting, escrow checks and B402 settlement stay in Studio's fixed code.

const CORE = process.env.MODULUS_CORE_URL ?? "http://127.0.0.1:8402";
const TICKER = /^[A-Z.]{1,8}$/;

export const service = {
  id: "modulus-council-verdict",
  title: "Council verdict on a tokenized stock (bStocks / Ondo / xStocks on BSC)",
  description:
    "Five elders (Night Watchman, Whale Watcher, Arbiter, Value Elder, Sentinel) vote; " +
    "the council returns BUY/SELL/HOLD/VETO with a calibrated confidence and every elder's reasoning.",
  priceUsd: "0.01",
  inputSchema: { type: "object", properties: { ticker: { type: "string" } }, required: ["ticker"] },
};

export async function doWork(input: { ticker: string }): Promise<Record<string, unknown>> {
  const ticker = String(input?.ticker ?? "").trim().toUpperCase();
  if (!TICKER.test(ticker)) throw new Error("ticker must be a US stock symbol, e.g. NVDA");
  const r = await fetch(`${CORE}/core/verdict/${ticker}`, { signal: AbortSignal.timeout(60_000) });
  if (!r.ok) throw new Error(`council unavailable: HTTP ${r.status}`);
  const verdict = (await r.json()) as Record<string, unknown>;
  return {
    agent: "modulus",
    ticker,
    verdict,
    disclaimer: "Research output, not investment advice. Calibrated on Jun-Oct 2026 bStock data.",
    servedAt: new Date().toISOString(),
  };
}

// End-to-end test: compile contracts/WeekendOracle.sol with solc, build a REAL Merkle commitment with the Python
// oracle (modulus/oracle.py), then run commit -> reveal -> verifyForecast -> grade in an in-memory EVM.
// Run: cd contracts && npm install && npm test
import solc from 'solc';
import { VM } from '@ethereumjs/vm';
import { Address, hexToBytes, bytesToHex } from '@ethereumjs/util';
import { Block } from '@ethereumjs/block';
import { Common, Chain, Hardfork } from '@ethereumjs/common';
import { Interface } from 'ethers';
import { execFileSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '..', '..');
let pass = 0, fail = 0;
const ok = (cond, name) => { if (cond) { pass++; console.log('  ok  ', name); } else { fail++; console.log('  FAIL', name); } };

// 1. compile
const src = fs.readFileSync(path.join(repo, 'contracts', 'WeekendOracle.sol'), 'utf8');
const out = JSON.parse(solc.compile(JSON.stringify({ language: 'Solidity', sources: { 'W.sol': { content: src } },
  settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: 'shanghai', outputSelection: { '*': { '*': ['abi', 'evm.bytecode.object'] } } } })));
const errs = (out.errors || []).filter(e => e.severity === 'error');
ok(errs.length === 0, 'WeekendOracle.sol compiles with solc ' + solc.version().split('+')[0]);
if (errs.length) { console.log(errs.map(e => e.formattedMessage).join('\n')); process.exit(1); }
const C = out.contracts['W.sol'].WeekendOracle; const I = new Interface(C.abi);

// 2. real commitment from the Python oracle
const py = `
import json, sys
sys.path.insert(0, ${JSON.stringify(repo)})
from modulus import oracle
fc = {"NVDA": {"gap_hat_bps": -35.2, "p_up": 0.4123}, "TSLA": {"gap_hat_bps": 80.5, "p_up": 0.6612},
      "AAPL": {"gap_hat_bps": 12.0, "p_up": 0.55}, "MU": {"gap_hat_bps": 150.0, "p_up": 0.7077}, "INTC": {"gap_hat_bps": -120.0, "p_up": 0.2923}}
wk = "2026-10-09"; tick = sorted(fc)
root, levels = oracle.merkle([oracle.leaf(wk, t, fc[t]) for t in tick])
import secrets; salt = secrets.token_bytes(32)
print(json.dumps({"root": root.hex(), "salt": salt.hex(), "commitment": oracle._h(root + salt).hex(),
  "pre": {t: f"{wk}|{t}|{fc[t]['gap_hat_bps']}|{fc[t]['p_up']}" for t in tick},
  "proofs": {t: oracle.proof(levels, i) for i, t in enumerate(tick)}, "inner": [levels[1][0].hex(), levels[1][1].hex()]}))`;
const M = JSON.parse(execFileSync(process.env.PYTHON || 'python3', ['-c', py]).toString());
const H = h => '0x' + h;

// 3. EVM
const common = new Common({ chain: Chain.Mainnet, hardfork: Hardfork.Shanghai });
const vm = await VM.create({ common });
const agent = new Address(hexToBytes('0x' + '11'.repeat(20)));
const other = new Address(hexToBytes('0x' + '22'.repeat(20)));
const fri = Date.UTC(2026, 9, 9) / 1000;   // Fri 9 Oct 2026 00:00 UTC
const blk = ts => Block.fromBlockData({ header: { timestamp: BigInt(ts), gasLimit: 30_000_000n, baseFeePerGas: 0n } }, { common });
async function deploy(enforce) {
  const r = await vm.evm.runCall({ caller: agent, data: hexToBytes('0x' + C.evm.bytecode.object + I.encodeDeploy([enforce]).slice(2)), gasLimit: 10_000_000n, block: blk(fri) });
  if (r.execResult.exceptionError) throw r.execResult.exceptionError;
  return r.createdAddress;
}
async function call(addr, fn, args, ts, from = agent) {
  const r = await vm.evm.runCall({ caller: from, to: addr, data: hexToBytes(I.encodeFunctionData(fn, args)), gasLimit: 5_000_000n, block: blk(ts) });
  const e = r.execResult;
  if (e.exceptionError) { let n = bytesToHex(e.returnValue); try { n = I.parseError(e.returnValue)?.name ?? n; } catch {} return { err: n }; }
  const res = I.decodeFunctionResult(fn, e.returnValue); return { ok: res.length === 1 ? res[0] : res, gas: e.executionGasUsed };
}
const W = 20261009, SAT = fri + 86400 + 12 * 3600, MON = fri + 3 * 86400 + 14 * 3600;
const a = await deploy(true);
ok((await call(a, 'fridayStart', [W], fri)).ok === BigInt(fri), 'weekId 20261009 decodes to Fri 9 Oct 00:00 UTC');
ok((await call(a, 'fridayStart', [20261010], fri)).err === 'BadWeekId', 'non-Friday weekId rejected');
ok((await call(a, 'commit', [W, H(M.commitment), 5], fri + 19 * 3600)).err === 'OutsideWindow', 'commit before Fri 20:00 UTC rejected');
ok((await call(a, 'commit', [W, H(M.commitment), 5], SAT, other)).err === 'NotAgent', 'commit by non-agent rejected');
ok((await call(a, 'commit', [W, H(M.commitment), 5], SAT)).err === undefined, 'commit inside the dark weekend accepted');
ok((await call(a, 'commit', [W, H(M.commitment), 5], SAT)).err === 'BadState', 'second commit (edit) rejected');
ok((await call(a, 'reveal', [W, H(M.root), H(M.salt)], fri + 3 * 86400 + 13 * 3600)).err === 'OutsideWindow', 'reveal before Monday 13:30 UTC rejected');
ok((await call(a, 'reveal', [W, H(M.root), H('00'.repeat(32))], MON)).err === 'CommitmentMismatch', 'reveal with wrong salt rejected');
ok((await call(a, 'reveal', [W, H(M.root), H(M.salt)], MON)).err === undefined, 'reveal after the open accepted');
for (const t of Object.keys(M.pre))
  ok((await call(a, 'verifyForecast', [W, M.pre[t], M.proofs[t].map(H)], MON)).ok === true, `Python Merkle proof verifies on-chain: ${t}`);
ok((await call(a, 'verifyForecast', [W, M.pre.NVDA.replace('0.4123', '0.9'), M.proofs.NVDA.map(H)], MON)).ok === false, 'tampered forecast fails');
ok((await call(a, 'verifyForecast', [W, '2026-10-09|' + M.inner[0], [H(M.inner[1])]], MON)).ok === false, 'inner-node second-preimage attack fails');
ok((await call(a, 'grade', [W, 7212, 2230], MON)).err === undefined, 'grade posted');
ok((await call(a, 'grade', [W, 9999, 1], MON)).err === 'BadState', 'grade cannot be overwritten');
const b = await deploy(false);
ok((await call(b, 'commit', [W, H(M.commitment), 5], fri - 2 * 86400)).err === undefined, 'testnet rehearsal deploy (window off) accepts a Wednesday commit');
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);

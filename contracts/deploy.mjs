// contracts/deploy.mjs — deploy WeekendOracle to BSC WITHOUT Foundry.
// Uses ethers v6 + solc 0.8.24 (both already in devDependencies) and the SAME compiler
// settings as test/oracle.test.mjs (optimizer 200, evmVersion cancun). The contract is a
// single self-contained file, so the source you deploy is also the exact BscScan verify input.
//
// Usage (PowerShell / bash — set the key in the environment, never on the command line):
//   PRIVATE_KEY=0x<64hex> node deploy.mjs --network testnet     # enforceWindow=false (rehearse mid-week)
//   PRIVATE_KEY=0x<64hex> node deploy.mjs --network mainnet      # enforceWindow=true  (commit/reveal window enforced on-chain)
//   PRIVATE_KEY=0x<64hex> node deploy.mjs --network mainnet --no-enforce-window
// Optional env: RPC_URL overrides the default public dataseed for the chosen network.
// Running with no PRIVATE_KEY still compiles and prints the verify inputs (a safe dry check).
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'
import { ethers } from 'ethers'

const require = createRequire(import.meta.url)
const solc = require('solc')
const HERE = path.dirname(fileURLToPath(import.meta.url))

const NETWORKS = {
  testnet: { chainId: 97, rpc: 'https://bsc-testnet-dataseed.bnbchain.org', explorer: 'https://testnet.bscscan.com', enforce: false },
  mainnet: { chainId: 56, rpc: 'https://bsc-dataseed.bnbchain.org',         explorer: 'https://bsctrace.com',         enforce: true  },
}
const flag = (f) => { const i = process.argv.indexOf(f); return i >= 0 ? (process.argv[i + 1] ?? true) : undefined }

const netName = flag('--network') || 'testnet'
const net = NETWORKS[netName]
if (!net) { console.error(`unknown --network "${netName}" (use testnet|mainnet)`); process.exit(1) }
let enforce = net.enforce
if (flag('--enforce-window')) enforce = true
if (flag('--no-enforce-window')) enforce = false

// 1. compile (identical settings to the test suite) — runs even without a key, as a dry check
const src = fs.readFileSync(path.join(HERE, 'WeekendOracle.sol'), 'utf8')
const out = JSON.parse(solc.compile(JSON.stringify({
  language: 'Solidity',
  sources: { 'WeekendOracle.sol': { content: src } },
  settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: 'cancun',
    outputSelection: { '*': { '*': ['abi', 'evm.bytecode.object'] } } },
})))
const errs = (out.errors || []).filter((e) => e.severity === 'error')
if (errs.length) { console.error(errs.map((e) => e.formattedMessage).join('\n')); process.exit(1) }
const art = out.contracts['WeekendOracle.sol'].WeekendOracle
const ctorArgs = ethers.AbiCoder.defaultAbiCoder().encode(['bool'], [enforce]).slice(2)
console.log(`compiled WeekendOracle with solc ${solc.version().split('+')[0]} (optimizer 200, evmVersion cancun)`)
console.log(`BscScan verify inputs → compiler v0.8.24, optimizer enabled/200, constructor arg (abi-encoded bool): ${ctorArgs}`)

// 2. deploy (needs the key)
const pk = process.env.PRIVATE_KEY
if (!pk || !/^0x[0-9a-fA-F]{64}$/.test(pk)) {
  console.error('\nset PRIVATE_KEY=0x<64 hex> in the environment to broadcast (dry compile done above).')
  process.exit(1)
}
const provider = new ethers.JsonRpcProvider(process.env.RPC_URL || net.rpc, net.chainId)
const wallet = new ethers.Wallet(pk, provider)
const bal = await provider.getBalance(wallet.address)
console.log(`\ndeployer ${wallet.address} — ${ethers.formatEther(bal)} BNB on chain ${net.chainId} (${netName})`)
if (bal === 0n) { console.error('deployer has 0 BNB for gas — fund it first (testnet faucet: https://www.bnbchain.org/en/testnet-faucet)'); process.exit(1) }

console.log(`deploying WeekendOracle(enforceWindow=${enforce}) ...`)
const factory = new ethers.ContractFactory(art.abi, art.evm.bytecode.object, wallet)
const c = await factory.deploy(enforce)
const txHash = c.deploymentTransaction().hash
console.log(`  broadcast tx: ${txHash}`)
await c.waitForDeployment()
const addr = await c.getAddress()
console.log(`\n✅ WeekendOracle live on ${netName}`)
console.log(`   address:  ${addr}`)
console.log(`   address:  ${net.explorer}/address/${addr}`)
console.log(`   deploy tx:${net.explorer}/tx/${txHash}`)
console.log(`   enforceWindow=${enforce}`)
console.log(`\nNext: put the address + tx link in README.md, export MODULUS_ORACLE_ADDR=${addr},`)
console.log(`then verify the single source file on ${net.explorer} with the inputs printed above.`)

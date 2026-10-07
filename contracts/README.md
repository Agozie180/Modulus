# WeekendOracle.sol

Modulus seals its Monday-open forecasts on BSC **before** the US opens, so the track record cannot be edited.

## foundry.toml (repo root)
```toml
[profile.default]
src = "contracts"
out = "out"
solc_version = "0.8.24"
evm_version = "cancun"
optimizer = true
optimizer_runs = 200

[rpc_endpoints]
bsc_testnet = "https://bsc-testnet-dataseed.bnbchain.org"   # chain id 97
bsc         = "https://bsc-dataseed.bnbchain.org"           # chain id 56

[etherscan]   # Etherscan API V2: one Etherscan key covers BscScan mainnet + testnet
bsc_testnet = { key = "${ETHERSCAN_API_KEY}", chain = 97 }
bsc         = { key = "${ETHERSCAN_API_KEY}", chain = 56 }
```

## Deploy to BSC testnet first (tBNB: https://www.bnbchain.org/en/testnet-faucet)
```bash
cast wallet import modulus --interactive            # keep the key out of shell history
forge build
cast chain-id --rpc-url bsc_testnet                 # -> 97
# constructor(bool enforceWindow): false on testnet so you can rehearse mid-week, true on mainnet
forge create contracts/WeekendOracle.sol:WeekendOracle \
  --rpc-url bsc_testnet --account modulus --broadcast \
  --constructor-args false \
  --verify --etherscan-api-key $ETHERSCAN_API_KEY
# (or verify later)
forge verify-contract <ADDR> contracts/WeekendOracle.sol:WeekendOracle --chain 97 \
  --constructor-args $(cast abi-encode "constructor(bool)" false) \
  --etherscan-api-key $ETHERSCAN_API_KEY --watch
```
Mainnet: same commands with `--rpc-url bsc`, `--chain 56` and `--constructor-args true`.

## Weekly cycle
```bash
python -m modulus oracle forecast
python -m modulus oracle commit                     # prints WeekendOracle.commit(20261009, 0x<commitment>, <n>)
cast send <ADDR> "commit(uint64,bytes32,uint32)" 20261009 0x<commitment> <n> --rpc-url bsc_testnet --account modulus
python -m modulus oracle reveal --week 2026-10-09   # prints reveal(20261009, 0x<root>, 0x<salt>)
cast send <ADDR> "reveal(uint64,bytes32,bytes32)" 20261009 0x<root> 0x<salt> --rpc-url bsc_testnet --account modulus
python -m modulus oracle grade --week 2026-10-09    # hit 0.7212 / brier 0.2230 -> 7212 / 2230
cast send <ADDR> "grade(uint64,int32,int32)" 20261009 7212 2230 --rpc-url bsc_testnet --account modulus
# anyone: prove one forecast from oracle/2026-10-09.json
cast call <ADDR> "verifyForecast(uint64,string,bytes32[])(bool)" 20261009 "2026-10-09|NVDA|-35.2|0.4123" "[0x..,0x..]" --rpc-url bsc_testnet
```
Gas: commit ≈ 70k, reveal ≈ 55k, grade ≈ 30k total gas (incl. 21k base each), i.e. a fraction of a cent at BSC's 0.05 gwei.
Note: the US open is 13:30 UTC during US daylight time and 14:30 UTC after 1 Nov 2026.

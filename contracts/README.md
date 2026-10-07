# WeekendOracle.sol

Modulus' Monday forecasts are sealed on BSC **before** the US opens, so the track record cannot be edited.

```
# deploy (Remix or Foundry) from the agent wallet
forge create contracts/WeekendOracle.sol:WeekendOracle --rpc-url https://bsc-dataseed.bnbchain.org --private-key $KEY

python -m modulus oracle forecast          # see the forecasts
python -m modulus oracle commit            # writes oracle/<week>.json, prints commit(weekId, commitment, n) calldata
python -m modulus oracle reveal --week 2026-10-09   # prints reveal(weekId, root, salt)
python -m modulus oracle grade  --week 2026-10-09   # scores vs the real Monday open -> oracle/scoreboard.json
```
Gas: commit + reveal + grade ~ 120k gas total, well under $0.05 on BSC.

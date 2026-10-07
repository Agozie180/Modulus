"""python -m modulus <scan|run|resolve|calibration|daemon|explain TICKER>"""
from __future__ import annotations
import argparse, json, sys
from .agent import Modulus


def main(argv=None):
    ap = argparse.ArgumentParser(prog="modulus", description="Council-of-Elders agent for bStocks on BNB Chain")
    ap.add_argument("cmd", choices=["scan", "run", "resolve", "calibration", "daemon", "explain", "oracle", "clock"])
    ap.add_argument("ticker", nargs="?")
    ap.add_argument("--tickers", help="comma list, e.g. NVDA,TSLA")
    ap.add_argument("--week", help="oracle week id (Friday, YYYY-MM-DD)")
    ap.add_argument("--nav", type=float, default=50.0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-audit", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "clock":
        from .clock import execution_policy
        print(json.dumps(execution_policy(), indent=2)); return
    if a.cmd == "oracle":
        return oracle_cmd(a)
    m = Modulus()
    tick = a.tickers.split(",") if a.tickers else ([a.ticker.upper()] if a.ticker else None)
    if a.cmd in ("scan", "explain"):
        res = m.scan(tick, audit=not a.no_audit)
        if a.json:
            print(json.dumps({"session": res["session"], "verdicts": [v.as_dict() for v in res["verdicts"]]}, default=str))
            return
        print(f"\nSession: {res['session']} | bStock market drift since the last US close: {res['market_drift']:+.2%}\n")
        for v in res["verdicts"][: (len(res["verdicts"]) if a.cmd == "explain" else 15)]:
            print(f"{v.action:5} {v.symbol:8} conf {v.confidence:.0%} dissent {v.dissent:.0%}  {v.headline}")
            if a.cmd == "explain":
                for o in v.opinions:
                    print(f"   - {o.elder:9} {'+-0'[[1,-1,0].index(o.direction)]} p={o.p:.2f}  {o.rationale}")
    elif a.cmd == "run":
        res, acted = m.run(a.nav, tick)
        for v, usd, r in acted:
            print(f"{v.action} {v.symbol} ${usd} -> {r.get('status')} {r.get('orderId', '')}")
        if not acted:
            print("Council found no trade worth its risk budget.")
    elif a.cmd == "resolve":
        print(f"resolved {m.resolve()} verdicts")
    elif a.cmd == "calibration":
        print(json.dumps(m.calibration_report(), indent=2))
    elif a.cmd == "daemon":
        m.daemon(a.nav)


def oracle_cmd(a):
    from . import oracle
    sub = (a.ticker or "forecast").lower()
    if sub == "backtest":
        print(json.dumps(oracle.backtest(), indent=2)); return
    if sub == "grade":
        s = oracle.grade(a.week)
        print(json.dumps(s, indent=2))
        if s.get("n"):
            print(f"WeekendOracle.grade({a.week.replace('-', '')}, {round(s['hit'] * 1e4)}, {round(s['brier'] * 1e4)})")
        return
    if sub == "reveal":
        rec = json.load(open(f"oracle/{a.week}.json"))
        print(f"reveal({a.week.replace('-', '')}, 0x{rec['root']}, 0x{rec['salt']})"); return
    res = Modulus().scan(audit=False)
    fc = oracle.forecast(res["moves"])
    if sub == "commit":
        if res["regime"] != "dark_weekend":
            print("WARNING: outside the on-chain commit window (Fri 20:00 - Sun 22:00 UTC). A mainnet WeekendOracle "
                  "(enforceWindow=true) will revert; rehearse on a testnet deploy with enforceWindow=false.")
        rec = oracle.commit(fc)
        print(f"week {rec['week']} | {len(fc)} forecasts | commitment 0x{rec['commitment']}")
        print(f"WeekendOracle.commit({rec['week'].replace('-', '')}, 0x{rec['commitment']}, {len(fc)})")
        return
    top = sorted(fc.items(), key=lambda kv: -abs(kv[1]["p_up"] - 0.5))[:15]
    note = "" if res["regime"] in ("dark_weekend", "dawn") else "  [weekday: model is weekend-trained, shown for demo]"
    print(f"Regime: {res['regime']} | next-open forecasts (P real stock opens above its last close){note}")
    for t, f in top:
        print(f"  {t:6} token {f['token_move_bps']:+7.0f} bps -> open {f['gap_hat_bps']:+6.0f} bps  P(up) {f['p_up']:.0%}")


if __name__ == "__main__":
    sys.exit(main())

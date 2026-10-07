"""python -m modulus <scan|run|resolve|calibration|daemon|explain TICKER>"""
from __future__ import annotations
import argparse, json, sys
from .agent import Modulus


def main(argv=None):
    ap = argparse.ArgumentParser(prog="modulus", description="Council-of-Elders agent for bStocks on BNB Chain")
    ap.add_argument("cmd", choices=["scan", "run", "resolve", "calibration", "daemon", "explain"])
    ap.add_argument("ticker", nargs="?")
    ap.add_argument("--tickers", help="comma list, e.g. NVDA,TSLA")
    ap.add_argument("--nav", type=float, default=50.0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-audit", action="store_true")
    a = ap.parse_args(argv)
    m = Modulus()
    tick = a.tickers.split(",") if a.tickers else ([a.ticker.upper()] if a.ticker else None)
    if a.cmd in ("scan", "explain"):
        res = m.scan(tick, audit=not a.no_audit)
        if a.json:
            print(json.dumps({"session": res["session"], "verdicts": [v.as_dict() for v in res["verdicts"]]}, default=str))
            return
        print(f"\nSession: {res['session']} | bStock market drift since Fri close: {res['market_drift']:+.2%}\n")
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


if __name__ == "__main__":
    sys.exit(main())

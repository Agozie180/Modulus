"""Does a bStock's weekend on-chain drift predict Monday's session?

Data : 1h on-chain candles for all 87 bStocks on BSC (research/fetch_history.py), Jun 24 - Oct 7 2026.
Event: Friday close (19:00 UTC candle, = 16:00 ET) -> Monday 13:00 UTC (pre-open) = weekend drift a.
Label: Monday 13:00 -> 20:00 UTC (regular session) = next move b.
Market-neutral: subtract each weekend's cross-sectional mean from a and b (weekends with >=10 tokens).
Run  : python research/weekend_study.py
"""
import json, math, statistics as st, collections, datetime as dt

H = json.load(open("data/hist_1h.json"))
ev = []
for s, c in H.items():
    px = {r[0]: float(r[4]) for r in c}
    for ts in px:
        d = dt.datetime.fromtimestamp(ts / 1000, dt.UTC)
        if d.weekday() == 4 and d.hour == 19:
            mon = ts + (2 * 24 + 17) * 3600_000
            end = mon + 7 * 3600_000
            if mon in px and end in px:
                ev.append((s, d.date().isoformat(), px[mon] / px[ts] - 1, px[end] / px[mon] - 1))
json.dump(ev, open("data/weekend_events.json", "w"))

by = collections.defaultdict(list)
for e in ev:
    by[e[1]].append(e)
rows = []
for d, v in by.items():
    if len(v) < 10:
        continue
    ma, mb = st.mean(e[2] for e in v), st.mean(e[3] for e in v)
    rows += [(d, a - ma, b - mb) for _, _, a, b in v]

print(f"events {len(ev)} | weekends with >=10 tokens: {len({r[0] for r in rows})}")
print("threshold  n   continue%  follow-pnl(bps, Monday session, pre-cost)")
for th in (0.003, 0.005, 0.01, 0.02):
    c = [r for r in rows if abs(r[1]) > th]
    cont = sum(1 for r in c if r[1] * r[2] > 0) / len(c)
    pnl = st.mean(math.copysign(1, r[1]) * r[2] for r in c) * 1e4
    print(f"  {th:>5.1%}  {len(c):>3}   {cont:6.1%}    {pnl:+6.1f}")
print("per weekend (|idio|>0.5%):")
for d in sorted({r[0] for r in rows}):
    c = [r for r in rows if r[0] == d and abs(r[1]) > 0.005]
    print(f"  {d}  n={len(c):>2}  continue {sum(1 for r in c if r[1]*r[2]>0)/max(1,len(c)):.0%}")
raw = [e for e in ev if abs(e[2]) > 0.005]
print(f"raw (not market-neutral) continuation: {sum(1 for e in raw if e[2]*e[3]>0)/len(raw):.1%} n={len(raw)} - fading the weekend lost {st.mean(-math.copysign(1,e[2])*e[3] for e in raw)*1e4:+.0f} bps")

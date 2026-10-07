"""What can actually be TRADED on the token? Entry Sunday 21:00 UTC (token), exits on the token.
Market-neutral (subtract weekend cross-sectional mean). Also: the US-close 'Friday gap' and
the hour CME futures reopen."""
import json, datetime as dt, statistics as st, collections
S=json.load(open('research/data24/spot_1h.json')); Y=json.load(open('research/data24/yahoo_1d.json'))
H=3600_000; ev=[]
for sym,k in S.items():
    px={r[0]:float(r[4]) for r in k}
    for r in Y.get(sym,[]):
        d=dt.datetime.fromtimestamp(r[0],dt.UTC).date()
        if d.weekday()!=4: continue
        f=int(dt.datetime(d.year,d.month,d.day,19,tzinfo=dt.UTC).timestamp()*1000)
        sun=f+(2*24+2)*H; mon=f+(3*24-6)*H  # Sun 21:00 close-candle ; Mon 13:00 candle (open 13:30 inside)
        x={n:px.get(t) for n,t in dict(f=f,sun=sun,cme=sun+2*H,mo=mon+H,mc=mon+7*H,tu=mon+24*H).items()}
        if None in x.values(): continue
        ev.append(dict(sym=sym,fri=d.isoformat(),w=x['sun']/x['f']-1,**{k:x[k]/x['sun']-1 for k in ('cme','mo','mc','tu')}))
by=collections.defaultdict(list)
for e in ev: by[e['fri']].append(e)
rows=[]
for w,v in by.items():
    if len(v)<8: continue
    m={k:st.mean(e[k] for e in v) for k in ('w','cme','mo','mc','tu')}
    rows+= [{k:(e[k]-m[k] if k in m else e[k]) for k in e} for e in v]
print('events',len(rows),'weekends',len({r['fri'] for r in rows}))
for th in (0.005,0.01,0.02):
    c=[r for r in rows if abs(r['w'])>th]
    print(f'|idio weekend drift|>{th:.1%} n={len(c)}', {k: round(st.mean((1 if r['w']>0 else -1)*r[k] for r in c)*1e4,1) for k in ('cme','mo','mc','tu')}, 'bps continuation from Sun21 (neg = fade wins)')
json.dump(rows,open('research/data24/tradable_rows.json','w'))

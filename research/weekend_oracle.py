"""THE WEEKEND ORACLE STUDY
Question: Wall Street is shut ~65.5 hours every weekend. bStocks keep trading on Binance Spot.
Does the weekend bStock price already know where the REAL stock opens on Monday?

Data : Binance Spot 1h klines for all 87 bStocks (24/7, Jun 11 - Oct 7 2026) + the real
       US-listed share from Yahoo (daily regular-session open/close).
Truth: real gap g = real next-session open / real last-session close - 1 (holidays handled).
Probe: token drift w(t) = token price at hour t of the weekend / token price at the US close - 1.
Score: error-reduction ER(t) = 1 - mean|g - w(t)| / mean|g|   (naive forecast = 'no change').
       hit rate = sign(w) == sign(g) on |w| > 0.25%.
Run  : python research/weekend_oracle.py   (after research/fetch_spot_24x7.py)
"""
import json, datetime as dt, statistics as st, collections, math
S=json.load(open('research/data24/spot_1h.json')); Y=json.load(open('research/data24/yahoo_1d.json'))
H=3600_000
def utc(ms): return dt.datetime.fromtimestamp(ms/1000,dt.UTC)
rows=[]   # per (sym, weekend)
for sym,k in S.items():
    if not k or not Y.get(sym): continue
    px={r[0]:float(r[4]) for r in k}               # candle open-time -> close price (close at +1h)
    tb={r[0]:(float(r[7]),float(r[10])) for r in k}  # quote vol, taker-buy quote vol
    days=[(utc(r[0]*1000).date(),r[1],r[4]) for r in Y[sym] if r[1] and r[4]]
    for i in range(len(days)-1):
        d0,_,c0=days[i]; d1,o1,_=days[i+1]
        if (d1-d0).days<3: continue                    # weekends (+ long weekends) only
        close_ms=int(dt.datetime(d0.year,d0.month,d0.day,19,tzinfo=dt.UTC).timestamp()*1000)  # candle 19-20 UTC closes at 16:00 ET (EDT)
        open_ms=int(dt.datetime(d1.year,d1.month,d1.day,13,tzinfo=dt.UTC).timestamp()*1000)   # 13:30 UTC open sits inside this candle
        if close_ms not in px: continue
        p0=px[close_ms]; g=o1/c0-1
        path={}; 
        for h in range(0,(open_ms-close_ms)//H):
            t=close_ms+h*H
            if t in px: path[h]=px[t]/p0-1
        wk=[tb[t] for t in range(close_ms+H,open_ms-14*H,H) if t in tb]   # pure weekend hours (before Sunday-night futures)
        qv=sum(a for a,b in wk); buy=sum(b for a,b in wk)
        basis=p0/c0-1
        rows.append(dict(sym=sym,fri=d0.isoformat(),g=g,path=path,hours=(open_ms-close_ms)//H,qv=qv,imb=(2*buy/qv-1) if qv else 0,basis=basis))
json.dump([{k:v for k,v in r.items() if k!='path'}|{'w_sun21':r['path'].get(r['hours']-16),'w_pre':r['path'].get(r['hours']-1)} for r in rows],open('research/data24/oracle_rows.json','w'))
print('weekend events',len(rows),'tickers',len({r['sym'] for r in rows}),'weekends',len({r['fri'] for r in rows}))
# discovery curve: hours BEFORE the Monday open
def score(key):
    v=[(r['g'],r['path'][r['hours']-key]) for r in rows if (r['hours']-key) in r['path']]
    if len(v)<50: return None
    ae0=st.mean(abs(g) for g,w in v); ae=st.mean(abs(g-w) for g,w in v)
    hit=[(g>0)==(w>0) for g,w in v if abs(w)>0.0025 and g!=0]
    corr=st.correlation([g for g,w in v],[w for g,w in v])
    return len(v),1-ae/ae0,sum(hit)/len(hit),corr,ae0*1e4,ae*1e4
curve={}
print('\nhrs before open | n | error cut vs "no change" | sign hit | corr | naive MAE bps | token MAE bps')
for hb in [64,60,56,52,48,44,40,36,32,28,24,20,17,16,15,14,12,10,8,6,4,2,1]:
    s=score(hb)
    if s: curve[hb]=s; print(f'  {hb:>3}h  {s[0]:>4}  {s[1]:+6.1%}  {s[2]:6.1%}  {s[3]:+.3f}  {s[4]:6.1f}  {s[5]:6.1f}')
json.dump(curve,open('research/data24/discovery_curve.json','w'))
# headline: Sunday 21:00 UTC (17:00 ET, one hour BEFORE CME equity futures reopen) = 16.5h before open

"""Deeper cuts on the Weekend Oracle rows: shrinkage (out-of-sample, leave-one-weekend-out),
market vs idiosyncratic split, taker-flow imbalance, Friday basis, and the liquidity clock."""
import json, statistics as st, collections, datetime as dt, math
R=[r for r in json.load(open('research/data24/oracle_rows.json')) if r['w_sun21'] is not None]
W=sorted({r['fri'] for r in R})
def ols(x,y):
    mx,my=st.mean(x),st.mean(y); b=sum((a-mx)*(c-my) for a,c in zip(x,y))/sum((a-mx)**2 for a in x); return b
out={}
# 1. leave-one-weekend-out shrinkage on Sunday 21:00 UTC token drift
ae0=ae1=aer=0;n=0
for w in W:
    tr=[r for r in R if r['fri']!=w]; te=[r for r in R if r['fri']==w]
    b=sum(r['w_sun21']*r['g'] for r in tr)/sum(r['w_sun21']**2 for r in tr)   # through origin
    for r in te: ae0+=abs(r['g']); aer+=abs(r['g']-r['w_sun21']); ae1+=abs(r['g']-b*r['w_sun21']); n+=1
bfull=sum(r['w_sun21']*r['g'] for r in R)/sum(r['w_sun21']**2 for r in R)
out['sun21']=dict(n=n,beta=bfull,naive_mae=ae0/n*1e4,raw_mae=aer/n*1e4,shrunk_mae_oos=ae1/n*1e4,err_cut_raw=1-aer/ae0,err_cut_shrunk_oos=1-ae1/ae0)
# 2. market vs idio
mk={w:(st.mean(r['g'] for r in R if r['fri']==w),st.mean(r['w_sun21'] for r in R if r['fri']==w)) for w in W}
xs=[mk[w][1] for w in W]; ys=[mk[w][0] for w in W]
out['market']=dict(weekends=len(W),corr=st.correlation(xs,ys),sign_hit=sum((a>0)==(b>0) for a,b in zip(xs,ys))/len(W))
idx=[(r['w_sun21']-mk[r['fri']][1],r['g']-mk[r['fri']][0]) for r in R]
big=[(a,b) for a,b in idx if abs(a)>0.005]
out['idio']=dict(corr=st.correlation([a for a,b in idx],[b for a,b in idx]),n_big=len(big),hit_big=sum((a>0)==(b>0) for a,b in big)/len(big),beta=ols([a for a,b in idx],[b for a,b in idx]))
# 3. flow imbalance (taker-buy share of weekend quote volume) -> idio gap
fi=[(r['imb'],r['g']-mk[r['fri']][0]) for r in R if r['qv']>20000]
q=sorted(fi); k=len(q)//5
out['flow']=dict(n=len(fi),corr=st.correlation([a for a,b in fi],[b for a,b in fi]),bottom_quintile_gap_bps=st.mean(b for a,b in q[:k])*1e4,top_quintile_gap_bps=st.mean(b for a,b in q[-k:])*1e4)
# 4. Friday-close basis (token vs real close, same minute)
bs=sorted(abs(r['basis']) for r in R)
out['basis_fri_close']=dict(median_bps=bs[len(bs)//2]*1e4,p90_bps=bs[int(.9*len(bs))]*1e4)
# 5. where is the token when it is WRONG? overshoot: |w|>|g| share
big2=[r for r in R if abs(r['w_sun21'])>0.01]
out['overshoot']=dict(n=len(big2),same_sign=sum((r['w_sun21']>0)==(r['g']>0) for r in big2)/len(big2),token_bigger_than_real=sum(abs(r['w_sun21'])>abs(r['g']) for r in big2)/len(big2))
# 6. liquidity clock from spot 1h (median quote volume by hour-of-week, ET-agnostic UTC)
S=json.load(open('research/data24/spot_1h.json'))
hv=collections.defaultdict(list); rg=collections.defaultdict(list)
for sym,k in S.items():
    for c in k:
        d=dt.datetime.fromtimestamp(c[0]/1000,dt.UTC); key=(d.weekday(),d.hour)
        hv[key].append(float(c[7])); 
        if float(c[4])>0: rg[key].append((float(c[2])-float(c[3]))/float(c[4]))
def med(x): x=sorted(x); return x[len(x)//2] if x else 0
tot=sum(sum(v) for v in hv.values())
wkend=sum(sum(v) for (wd,h),v in hv.items() if wd==5 or (wd==6 and h<22) or (wd==4 and h>=20))
out['liquidity']=dict(weekend_share_of_volume=wkend/tot,weekend_share_of_hours=(4+24+22)/168,
  median_hourly_qv_regular=med([x for (wd,h),v in hv.items() if wd<5 and 14<=h<20 for x in v]),
  median_hourly_qv_weekend=med([x for (wd,h),v in hv.items() if wd==5 for x in v]),
  median_range_regular_bps=med([x for (wd,h),v in rg.items() if wd<5 and 14<=h<20 for x in v])*1e4,
  median_range_weekend_bps=med([x for (wd,h),v in rg.items() if wd==5 for x in v])*1e4)
clock={f'{wd}-{h:02d}':med(hv[(wd,h)]) for wd in range(7) for h in range(24)}
json.dump(clock,open('research/data24/liquidity_clock.json','w'))
json.dump(out,open('research/data24/oracle_deep.json','w'),indent=1); print(json.dumps(out,indent=1))

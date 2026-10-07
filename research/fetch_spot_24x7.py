"""Fetch the 24/7 Binance Spot order-book history for every bStock (public, keyless market data
mirror data-api.binance.vision) + the real US-listed share from Yahoo (daily and 1h incl. pre/post).
Output: research/data24/spot_1h.json, yahoo_1d.json, yahoo_1h.json"""
import json, urllib.request, time, concurrent.futures as cf
L=[x for x in json.load(open('data/list_bstock.json'))['data'] if x['chainId']=='56']
SP='https://data-api.binance.vision/api/v3/klines'
def get(u,h=None):
    for a in range(4):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers=h or {'User-Agent':'modulus-research'}),timeout=30))
        except Exception as e: err=e; time.sleep(1+a)
    return None
def spot(x):
    s=x['cs']; out=[]; st=1780000000000
    while True:
        k=get(f'{SP}?symbol={s}&interval=1h&startTime={st}&limit=1000')
        if not k or isinstance(k,dict): break
        out+=k
        if len(k)<1000: break
        st=k[-1][0]+1
    return x['symbol'],out
def yahoo(t,iv,rng):
    d=get(f'https://query1.finance.yahoo.com/v8/finance/chart/{t}?interval={iv}&range={rng}&includePrePost=true',{'User-Agent':'Mozilla/5.0'})
    try:
        r=d['chart']['result'][0]; q=r['indicators']['quote'][0]
        return [[ts,q['open'][i],q['high'][i],q['low'][i],q['close'][i],q['volume'][i]] for i,ts in enumerate(r['timestamp']) if q['close'][i] is not None]
    except Exception: return []
with cf.ThreadPoolExecutor(8) as ex:
    S=dict(ex.map(spot,L))
    tick={x['symbol']:x['ticker'] for x in L}
    Y1=dict(zip(tick, ex.map(lambda s: yahoo(tick[s].replace('.','-'),'1d','6mo'),tick)))
    Yh=dict(zip(tick, ex.map(lambda s: yahoo(tick[s].replace('.','-'),'1h','6mo'),tick)))
for n,o in (('spot_1h',S),('yahoo_1d',Y1),('yahoo_1h',Yh)): json.dump(o,open(f'research/data24/{n}.json','w'))
print('spot',sum(1 for v in S.values() if v),sum(len(v) for v in S.values()),'y1d',sum(1 for v in Y1.values() if v),'y1h',sum(1 for v in Yh.values() if v))

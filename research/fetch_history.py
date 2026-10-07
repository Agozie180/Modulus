import json,urllib.request,concurrent.futures as cf,time
U='https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/dex/market/token/kline/ai'
H={'Accept-Encoding':'identity','User-Agent':'binance-web3/1.1 (Skill)'}
L=[x for x in json.load(open('data/list_bstock.json'))['data'] if x['chainId']=='56']
def fetch(x):
    c=x['contractAddress']; allc={}; end=None
    for _ in range(14):
        q=f'{U}?chainId=56&contractAddress={c}&interval=1h&limit=300'+(f'&endTime={end}' if end else '')
        for a in range(3):
            try: d=json.load(urllib.request.urlopen(urllib.request.Request(q,headers=H),timeout=25)); break
            except Exception: time.sleep(1.5); d=None
        k=((d or {}).get('data') or {}).get('klineInfos') or []
        if not k: break
        for r in k: allc[r[0]]=r
        e=min(r[0] for r in k)-1
        if end is not None and e>=end: break
        end=e
        if len(k)<300: break
    return x['symbol'],sorted(allc.values())
out={}
with cf.ThreadPoolExecutor(6) as ex:
    for s,c in ex.map(fetch,L): out[s]=c
json.dump(out,open('data/hist_1h.json','w'))
print({k:len(v) for k,v in list(out.items())[:10]}, sum(len(v) for v in out.values()))

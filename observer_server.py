#!/usr/bin/env python3
"""Public, read-only market observation. No AI, orders, bots or account endpoints."""
import concurrent.futures
import json
import os
import threading
import time
import urllib.parse
from pathlib import Path

ROOT=Path(__file__).resolve().parent
os.environ.setdefault('MARKET_DECK_DATA',str(ROOT/'data/observer'))
import server as core

PORT=int(os.environ.get('DECKLAB_OBSERVER_PORT','8790'))
STATUS={'started':time.time(),'last_cycle':None}

def init():
    with core.db() as c:
        c.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS assets(symbol TEXT PRIMARY KEY,name TEXT,kind TEXT,region TEXT,currency TEXT DEFAULT 'USD',provider TEXT,pair TEXT,tracked INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS quotes(symbol TEXT PRIMARY KEY,price REAL,change REAL,volume REAL,asof REAL,fetched REAL,source TEXT,status TEXT);
        CREATE TABLE IF NOT EXISTS history(symbol TEXT,ts REAL,price REAL,PRIMARY KEY(symbol,ts));
        CREATE TABLE IF NOT EXISTS news(id TEXT PRIMARY KEY,title TEXT,url TEXT,source TEXT,published TEXT,seen REAL,published_ts REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS providers(name TEXT PRIMARY KEY,state TEXT,message TEXT,checked REAL);
        ''')
        for symbol,name,kind,region in core.SEEDS:
            c.execute('INSERT OR IGNORE INTO assets VALUES(?,?,?,?,?,?,?,1)',(symbol,name,kind,region,'USD','Yahoo Finance',None))

def crypto():
    catalog=core.getjson('https://api.kraken.com/0/public/AssetPairs')
    if catalog.get('error'):raise ValueError('Kraken spot catalog unavailable')
    with core.db() as c:
        for pair,a in catalog['result'].items():
            name=a.get('wsname','')
            if not name.endswith('/USD') or a.get('status')!='online' or '.d' in pair:continue
            symbol=name.replace('XBT','BTC').replace('XDG','DOGE')
            base=symbol.split('/')[0]
            kind='forex' if base in core.markets.FIAT else 'commodity_token' if base in ('PAXG','XAUT') else 'crypto'
            c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,1) ON CONFLICT(symbol) DO UPDATE SET pair=excluded.pair,kind=excluded.kind',
                      (symbol,symbol,kind,'Global','USD','Kraken',pair))
    payload=core.getjson('https://api.kraken.com/0/public/Ticker')
    if payload.get('error'):raise ValueError('Kraken spot ticker unavailable')
    now=time.time();count=0
    with core.db() as c:
        for a in c.execute("SELECT symbol,pair FROM assets WHERE provider='Kraken'").fetchall():
            quote=payload['result'].get(a['pair'])
            if not quote:continue
            price=float(quote['c'][0]);opening=float(quote['o'])
            core.store(c,a['symbol'],price,(price/opening-1)*100 if opening else 0,float(quote['v'][1]),now,'Kraken spot REST · receipt time, exchange time unavailable');count+=1
    core.provider('Kraken spot','ok',str(count)+' spot quotes observed; no execution or exchange timestamp claim')

def loop():
    jobs={'Kraken spot':(crypto,30),'Yahoo Finance':(core.stocks,120),'NSE public observations':(core.nse_quotes,120)}
    jobs.update({name:(lambda n=name,u=url:core.news_feed((n,u)),300) for name,url in core.FEEDS})
    due={name:0. for name in jobs};running={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        while not core.STOP.is_set():
            now=time.time()
            for name,future in list(running.items()):
                if not future.done():continue
                try:future.result()
                except Exception as exc:core.feed_failure(name,type(exc).__name__+': public feed unavailable')
                del running[name];STATUS['last_cycle']=now
            for name in sorted(jobs,key=lambda n:(n not in ('Kraken spot','Yahoo Finance','NSE public observations'),due[n])):
                if len(running)>=4:break
                if name in running or due[name]>now:continue
                fn,interval=jobs[name];due[name]=now+interval;running[name]=pool.submit(fn)
            core.STOP.wait(1)

def state(params):
    query=str(params.get('q',[''])[0])[:80]
    offset=max(0,min(100000,int(params.get('offset',['0'])[0])))
    limit=max(1,min(100,int(params.get('limit',['80'])[0])))
    with core.db() as c:
        args=('%'+query+'%','%'+query+'%')
        where="a.tracked=1 AND (a.symbol LIKE ? OR a.name LIKE ?)"
        if 'pins' in params:
            pins=json.loads(params['pins'][0])
            if not isinstance(pins,list) or len(pins)>100 or any(not isinstance(s,str) or len(s)>40 for s in pins):raise ValueError('Invalid watchlist')
            where+=' AND a.symbol IN ('+','.join('?' for _ in pins)+')' if pins else ' AND 0'
            args=(*args,*pins)
        total=c.execute('SELECT COUNT(*) FROM assets a WHERE '+where,args).fetchone()[0]
        assets=core.rows(c,'SELECT a.symbol,a.name,a.kind,a.region,a.currency,q.price,q.change,q.volume,q.asof,q.fetched,q.source FROM assets a LEFT JOIN quotes q USING(symbol) WHERE '+where+" ORDER BY CASE a.symbol WHEN 'BTC/USD' THEN 0 WHEN 'ETH/USD' THEN 1 WHEN 'SOL/USD' THEN 2 WHEN 'AAPL' THEN 3 ELSE 4 END,a.symbol LIMIT ? OFFSET ?",(*args,limit,offset))
        news=core.rows(c,'SELECT title,url,source,published_ts,seen FROM news ORDER BY published_ts DESC,seen DESC LIMIT 40')
        providers=core.rows(c,'SELECT name,state,message,checked FROM providers ORDER BY name')
        signals=core.signals(c)
        observed=c.execute('SELECT COUNT(*) FROM quotes').fetchone()[0]
    for a in assets:
        receipt_only=(a['source'] or '').startswith('Kraken spot')
        a['exchange_timestamp']=None if receipt_only else a['asof']
        a['timestamp_basis']='receipt-time' if receipt_only else 'provider-reported observation'
        a['fresh']=bool(a['asof'] and a['fetched'] and 0<=time.time()-a['asof']<=(120 if a['kind']=='crypto' else 300) and 0<=time.time()-a['fetched']<=120)
    # Deterministic descriptors, never buy/sell actions or execution recommendations.
    research=[{k:s[k] for k in ('symbol','rsi','mean','momentum','samples','asof','fresh')} for s in signals]
    for item in research:item['fresh']=bool(item['asof'] and 0<=time.time()-item['asof']<=120)
    return {'mode':'live-observation','ai_enabled':False,'execution_enabled':False,'now':time.time(),
            'runtime':dict(STATUS),'assets':assets,'total':total,'offset':offset,'limit':limit,'observed':observed,
            'news':news,'providers':providers,'research':research,
            'notice':'Public feeds can be delayed, partial or unavailable. Kraken times are receipt times. No AI, forecasts, account data or order execution. Indicators need at least 15 recorded samples.'}

class Handler(core.Handler):
    def valid_host(self):
        if super().valid_host():return True
        values=self.headers.get_all('Host',[])
        name=os.environ.get('CODESPACE_NAME','')
        domain=os.environ.get('GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN','app.github.dev')
        expected=f'{name}-{PORT}.{domain}'
        return bool(os.environ.get('CODESPACES')=='true' and name and len(values)==1 and values[0].lower()==expected.lower())

    def do_POST(self):
        self.request_id=core.secrets.token_hex(12)
        return self.send({'error':'Public observation is read-only. AI and execution are disabled.'},403)

    def do_GET(self):
        self.request_id=core.secrets.token_hex(12)
        if not self.valid_host():return self.send({'error':'Unexpected host'},403)
        path=urllib.parse.urlsplit(self.path);params=urllib.parse.parse_qs(path.query)
        try:
            if path.path=='/api/health':return self.send({'ok':True,'mode':'live-observation','ai_enabled':False,'execution_enabled':False})
            if path.path=='/api/observer/state':return self.send(state(params))
            if path.path=='/api/observer/history':
                symbol=str(params.get('symbol',['BTC/USD'])[0])[:40]
                with core.db() as c:return self.send(core.rows(c,'SELECT ts,price FROM (SELECT ts,price FROM history WHERE symbol=? ORDER BY ts DESC LIMIT 96) ORDER BY ts',(symbol,)))
            allowed={'/':'observer.html','/observer.js':'observer.js','/observer.css':'observer.css','/style.css':'style.css','/vendor/new-era.js':'vendor/new-era.js'}
            if path.path not in allowed:return self.send({'error':'Not found'},404)
            p=ROOT/'static'/allowed[path.path]
            return self.send(p.read_bytes(),ctype='text/html; charset=utf-8' if p.suffix=='.html' else 'application/javascript' if p.suffix=='.js' else 'text/css')
        except (ValueError,TypeError):return self.send({'error':'Invalid query'},400)
        except Exception:return self.send({'error':'Observation temporarily unavailable'},503)

def main():
    if os.environ.get('CODESPACES')!='true':raise SystemExit('Live observer entry point is restricted to the explicitly authorized Codespace.')
    if core.DATA.resolve()!=(ROOT/'data/observer').resolve():raise SystemExit('Observer requires its separate data/observer workspace')
    init();threading.Thread(target=loop,name='public-market-feeds',daemon=True).start()
    httpd=core.ThreadingHTTPServer(('0.0.0.0',PORT),Handler)
    try:httpd.serve_forever()
    finally:core.STOP.set();httpd.server_close()

if __name__=='__main__':main()

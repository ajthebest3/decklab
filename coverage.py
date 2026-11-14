"""Source-backed listing directories, global discovery and on-demand instrument facts."""
import concurrent.futures, csv, hashlib, io, json, math, re, threading, time, urllib.parse

CATALOGS={
 'NSE equities':('https://archives.nseindia.com/content/equities/EQUITY_L.csv','nse'),
 'Nasdaq listings':('https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt','nasdaq'),
 'Other US listings':('https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt','other'),
}
SUFFIXES={'.NS':('India','NSE','INR'),'.BO':('India','BSE','INR'),'.L':('UK','London',''),'.T':('Japan','Tokyo','JPY'),'.HK':('Hong Kong','Hong Kong','HKD'),'.SS':('China','Shanghai','CNY'),'.SZ':('China','Shenzhen','CNY'),'.AX':('Australia','ASX','AUD'),'.TO':('Canada','Toronto','CAD'),'.V':('Canada','TSX Venture','CAD'),'.PA':('France','Paris','EUR'),'.DE':('Germany','Xetra','EUR'),'.AS':('Netherlands','Amsterdam','EUR'),'.SW':('Switzerland','Swiss','CHF'),'.KS':('South Korea','Korea','KRW'),'.KQ':('South Korea','KOSDAQ','KRW'),'.SA':('Brazil','Sao Paulo','BRL'),'.SI':('Singapore','Singapore','SGD')}
def listing_market(symbol,exchange=''):
 for suffix,info in SUFFIXES.items():
  if symbol.endswith(suffix):return info
 return ('US',exchange or 'US','USD') if '.' not in symbol else ('Other',exchange or 'Provider exchange','')

def parse_catalog(text,kind):
 out=[]
 reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')),delimiter=',' if kind=='nse' else '|')
 if not reader.fieldnames or not ({'SYMBOL','NAME OF COMPANY'}<=set(reader.fieldnames) if kind=='nse' else 'Security Name' in reader.fieldnames):raise ValueError('Unexpected listing file columns')
 for row in reader:
  if kind=='nse':
   raw=(row.get('SYMBOL') or '').strip();name=(row.get('NAME OF COMPANY') or '').strip()
   if not re.fullmatch(r'[A-Z0-9&_-]{1,30}',raw) or not name:continue
   out.append({'symbol':raw+'.NS','name':name,'kind':'equity','region':'India','exchange':'NSE','currency':'INR','listing_symbol':raw,'isin':(row.get(' ISIN NUMBER') or row.get('ISIN NUMBER') or '').strip()})
  else:
   if row.get('Test Issue')!='N':continue
   raw=(row.get('Symbol') or row.get('ACT Symbol') or '').strip();name=(row.get('Security Name') or '').strip()
   if not re.fullmatch(r'[A-Za-z0-9.$^/_-]{1,30}',raw) or not name:continue
   security='etf' if row.get('ETF')=='Y' else 'warrant' if re.search(r'\bwarrants?\b',name,re.I) else 'right' if re.search(r'\brights?\b',name,re.I) else 'preferred' if re.search(r'\bpreferred\b',name,re.I) else 'unit' if re.search(r'\bunits?\b',name,re.I) else 'equity'
   symbol=raw.replace('.','-').replace('/','-')
   exchange='Nasdaq' if kind=='nasdaq' else {'N':'NYSE','A':'NYSE American','P':'NYSE Arca','Z':'Cboe','V':'IEX'}.get(row.get('Exchange'),row.get('Exchange') or 'US')
   out.append({'symbol':symbol,'name':name,'kind':security,'region':'US','exchange':exchange,'currency':'USD','listing_symbol':raw,'isin':''})
 if not out:raise ValueError('Listing file contains no usable records')
 return out

class MarketCoverage:
 def __init__(self,data,db,rows,fetch,getjson,provider,stop):
  self.data,self.db,self.rows,self.fetch,self.getjson,self.provider,self.stop=data,db,rows,fetch,getjson,provider,stop
  self.lock=threading.Lock();self.cache={};self.cache_lock=threading.Lock();self.detail_lock=threading.BoundedSemaphore(4)
 def init(self,c):
  c.executescript('''CREATE TABLE IF NOT EXISTS instrument_directory(symbol TEXT PRIMARY KEY,exchange TEXT,listing_symbol TEXT,isin TEXT,source TEXT,source_url TEXT,updated REAL,active INTEGER DEFAULT 1);
   CREATE TABLE IF NOT EXISTS catalog_sources(name TEXT PRIMARY KEY,url TEXT,checked REAL,imported REAL,count INTEGER,state TEXT,message TEXT,sha256 TEXT);
   CREATE TABLE IF NOT EXISTS instrument_facts(symbol TEXT PRIMARY KEY,updated REAL,body TEXT);
   CREATE INDEX IF NOT EXISTS news_published_order ON news(published_ts DESC,seen DESC);
   CREATE INDEX IF NOT EXISTS news_source_order ON news(source,published_ts DESC);
  ''')
 def import_catalog(self,name,payload):
  url,kind=CATALOGS[name];parsed=parse_catalog(payload.decode('utf-8-sig'),kind);now=time.time()
  with self.db() as c:
   c.execute('BEGIN IMMEDIATE');c.execute('UPDATE instrument_directory SET active=0 WHERE source=?',(name,))
   for a in parsed:
    c.execute("INSERT INTO assets(symbol,name,kind,region,currency,provider,tracked) VALUES(?,?,?,?,?,'Yahoo Finance',0) ON CONFLICT(symbol) DO UPDATE SET name=excluded.name,region=excluded.region WHERE assets.provider='Yahoo Finance'",(a['symbol'],a['name'],a['kind'],a['region'],a['currency']))
    c.execute('INSERT OR REPLACE INTO instrument_directory VALUES(?,?,?,?,?,?,?,1)',(a['symbol'],a['exchange'],a['listing_symbol'],a['isin'],name,url,now))
   c.execute('INSERT OR REPLACE INTO catalog_sources VALUES(?,?,?,?,?,?,?,?)',(name,url,now,now,len(parsed),'ok','Listing directory only; quote availability is verified separately.',hashlib.sha256(payload).hexdigest()))
  self.provider(name,'ok',f'{len(parsed):,} securities imported; directory, not a live quote feed')
  return len(parsed)
 def refresh_catalogs(self):
  if not self.lock.acquire(blocking=False):return
  try:
   with self.db() as c:seen={r['name']:r['checked'] for r in c.execute('SELECT name,checked FROM catalog_sources')}
   due=[name for name in CATALOGS if time.time()-seen.get(name,0)>=86400]
   def load(name):
    url,_=CATALOGS[name]
    try:return name,self.import_catalog(name,self.fetch(url))
    except Exception:
     with self.db() as c:c.execute("INSERT INTO catalog_sources(name,url,checked,state,message,count) VALUES(?,?,?,'error','Directory refresh unavailable; last successful rows retained.',0) ON CONFLICT(name) DO UPDATE SET checked=excluded.checked,state=excluded.state,message=excluded.message",(name,url,time.time()))
     self.provider(name,'error','Directory refresh unavailable; last successful rows retained.')
     return name,0
   with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:return dict(pool.map(load,due))
  finally:self.lock.release()
 def loop(self):
  while not self.stop.is_set():
   try:self.refresh_catalogs()
   except Exception:pass
   self.stop.wait(3600)
 def status(self,c=None):
  if c is None:
   with self.db() as con:return self.status(con)
  return {'directories':self.rows(c,'SELECT * FROM catalog_sources ORDER BY name'),'regions':self.rows(c,'SELECT region,COUNT(*) AS count FROM assets GROUP BY region ORDER BY count DESC'),'tracked':c.execute('SELECT COUNT(*) FROM assets WHERE tracked=1').fetchone()[0],
   'limits':['Directories are listings, not continuous quote subscriptions.','Global search depends on Yahoo provider coverage; not every exchange is included.','BSE bulk directory is unavailable from this host (HTTP 403); BSE discovery is via provider search/exact symbols.','Indian shares are research-only in the current USD paper account.','No paid consolidated streaming feed, full financial-statement feed or exhaustive news license is configured.']}
 def search_remote(self,q):
  key=q.casefold()
  with self.cache_lock:
   saved=self.cache.get(key)
   if saved and time.time()-saved[0]<300:return saved[1]
  provider_query=re.sub(r'\b(?:NSE|BSE)\b','',q,flags=re.I).strip() or q
  j=self.getjson('https://query1.finance.yahoo.com/v1/finance/search?'+urllib.parse.urlencode({'q':provider_query,'quotesCount':20,'newsCount':0}))
  out=[]
  for item in j.get('quotes',[]):
   symbol=item.get('symbol','');name=item.get('longname') or item.get('shortname')
   if not re.fullmatch(r'[A-Za-z0-9^=./_&-]{1,40}',symbol) or not name:continue
   kind={'EQUITY':'equity','ETF':'etf','INDEX':'index','MUTUALFUND':'fund','FUTURE':'commodity','CURRENCY':'forex','CRYPTOCURRENCY':'crypto'}.get(item.get('quoteType'),'other')
   if kind=='crypto':continue # Keep exchange spot pairs distinct from provider crypto indices.
   region,exchange,currency=listing_market(symbol,item.get('exchDisp',''))
   out.append({'symbol':symbol,'name':name,'kind':kind,'region':region,'exchange':item.get('exchDisp') or exchange,'currency':currency,'provider':'Yahoo Finance','tracked':0,'price':None,'source':'Yahoo global search','listing_status':'Provider search result; quote not verified'})
  with self.db() as c:
   for a in out:
    c.execute('INSERT OR IGNORE INTO assets(symbol,name,kind,region,currency,provider,tracked) VALUES(?,?,?,?,?,?,0)',tuple(a[x] for x in ['symbol','name','kind','region','currency','provider']))
    c.execute("INSERT OR IGNORE INTO instrument_directory VALUES(?,?,?,'','Yahoo global search','https://finance.yahoo.com',?,1)",(a['symbol'],a['exchange'],a['symbol'],time.time()))
  with self.cache_lock:
   if len(self.cache)>=128:self.cache.pop(next(iter(self.cache)))
   self.cache[key]=(time.time(),out)
  return out
 def catalog(self,params):
  get=lambda k,d='':params.get(k,[d])[0]
  q=get('q').strip()[:80];region=get('region');kind=get('kind');page=max(0,min(10000,int(get('page','0'))));limit=max(1,min(100,int(get('limit','40'))));remote='not_requested'
  if len(q)>=2 and get('remote')=='1':
   try:self.search_remote(q);remote='ok'
   except Exception:remote='unavailable'
  where=['(d.active IS NULL OR d.active=1 OR a.tracked=1)'];args=[]
  for token in q.split()[:6]:where.append('(a.symbol LIKE ? OR a.name LIKE ? OR d.isin LIKE ? OR d.exchange LIKE ?)');args.extend(['%'+token+'%']*4)
  if region and region!='all':where.append('a.region=?');args.append(region)
  if kind and kind!='all':where.append('a.kind=?');args.append(kind)
  if get('tracked')=='1':where.append('a.tracked=1')
  clause=' AND '.join(where)
  with self.db() as c:
   total=c.execute('SELECT COUNT(*) FROM assets a LEFT JOIN instrument_directory d USING(symbol) WHERE '+clause,args).fetchone()[0]
   items=self.rows(c,"SELECT a.*,d.exchange,d.source AS directory_source,d.source_url,d.updated AS directory_updated,d.isin,d.active,q.price,q.change,q.asof,q.source,q.status FROM assets a LEFT JOIN instrument_directory d USING(symbol) LEFT JOIN quotes q USING(symbol) WHERE "+clause+" ORDER BY CASE WHEN a.symbol=? THEN 0 WHEN a.symbol LIKE ? THEN 1 ELSE 2 END,a.tracked DESC,a.name,a.symbol LIMIT ? OFFSET ?",(*args,q.upper(),q.upper()+'%',limit,page*limit))
  return {'items':items,'total':total,'page':page,'limit':limit,'remote':remote,'note':'Catalog listings are searchable; prices are fetched only for opened/tracked instruments.'}
 def instrument(self,symbol):
  if not re.fullmatch(r'[A-Za-z0-9^=./_&-]{1,40}',symbol):raise ValueError('Invalid instrument symbol')
  with self.db() as c:
   a=c.execute('SELECT * FROM assets WHERE symbol=?',(symbol,)).fetchone();cached=c.execute('SELECT * FROM instrument_facts WHERE symbol=?',(symbol,)).fetchone()
   if cached and time.time()-cached['updated']<300:
    result=json.loads(cached['body']);result['asset']['tracked']=a['tracked'] if a else 0;return result
  if not a:
   self.search_remote(symbol)
   with self.db() as c:a=c.execute('SELECT * FROM assets WHERE symbol=?',(symbol,)).fetchone()
  if not a:raise ValueError('The symbol was not found by the configured provider')
  a=dict(a);meta={};error=''
  if a['provider']=='Yahoo Finance':
   if not self.detail_lock.acquire(blocking=False):raise ValueError('Several instruments are loading. Try again shortly.')
   try:
    j=self.getjson('https://query1.finance.yahoo.com/v8/finance/chart/'+urllib.parse.quote(symbol,safe='')+'?range=1d&interval=5m');meta=j['chart']['result'][0]['meta']
    with self.db() as c:
     c.execute('UPDATE assets SET currency=? WHERE symbol=?',(meta.get('currency') or a['currency'],symbol))
   except Exception:error='Quote details are unavailable from the indicative provider. The directory listing is retained.'
   finally:self.detail_lock.release()
  with self.db() as c:
   a=dict(c.execute('SELECT a.*,q.price,q.change,q.asof,q.source,q.status FROM assets a LEFT JOIN quotes q USING(symbol) WHERE symbol=?',(symbol,)).fetchone())
   directory=c.execute('SELECT * FROM instrument_directory WHERE symbol=?',(symbol,)).fetchone()
   terms=[symbol.split('.')[0]]+[word for word in re.findall(r'[A-Za-z]{4,}',a['name']) if word.lower() not in ('limited','company','corporation','incorporated','common','stock','shares','ordinary','the')][:1]
   news=self.rows(c,'SELECT * FROM news WHERE '+ ' OR '.join('title LIKE ?' for _ in terms)+' ORDER BY published_ts DESC,seen DESC LIMIT 12',['%'+word+'%' for word in terms])
  price=meta.get('regularMarketPrice');previous=meta.get('chartPreviousClose') or meta.get('previousClose')
  if isinstance(price,(int,float)) and math.isfinite(price):a.update(price=price,asof=meta.get('regularMarketTime'),change=(price/previous-1)*100 if previous else None,source='Yahoo Finance · indicative',currency=meta.get('currency') or a['currency'])
  facts={key:meta.get(key) for key in ['longName','shortName','exchangeName','fullExchangeName','instrumentType','currency','regularMarketTime','regularMarketPrice','regularMarketVolume','regularMarketDayHigh','regularMarketDayLow','fiftyTwoWeekHigh','fiftyTwoWeekLow','chartPreviousClose','exchangeTimezoneName']}
  result={'asset':a,'listing':dict(directory) if directory else None,'facts':facts,'news':news,'error':error,'fetched':time.time(),'limitations':['Provider quote and range facts only; audited financial statements and complete fundamentals are not available.','Matching archived headlines are not a complete company news feed.','A listing does not guarantee a valid quote or trading eligibility.']}
  if not error:
   with self.db() as c:c.execute('INSERT OR REPLACE INTO instrument_facts VALUES(?,?,?)',(symbol,time.time(),json.dumps(result,allow_nan=False)))
  return result

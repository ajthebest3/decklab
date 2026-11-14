"""Public executable market evidence. No private orders or broker credentials."""
import math
import time
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

FIAT = {'EUR', 'GBP', 'AUD', 'CAD', 'CHF', 'JPY'}
TOKEN_KINDS = {'tokenized_equity', 'tokenized_etf'}
# Conservative known ETF classification; other xStocks retain the tokenized label.
ETFS = {'SPY','QQQ','VOO','VTI','VT','VUG','VXUS','IWM','IJR','GLD','SLV','GDX','SGOV','TBLL','EWG','EWQ','EWU','EWY','FEZ','VGK','SCHF','IEMG','COPX','PALL','PPLT','URA','XLE','XOP','SMH','SOXX','TQQQ','SOXL','BITX','NLR','ITA'}

def kraken_class(asset):
    return 'tokenized_asset' if asset['kind'] in TOKEN_KINDS else 'currency'

def nse_supported(asset):
    return asset['symbol'].endswith('.NS') and asset['kind'] in ('equity','etf') and asset['currency']=='INR' and asset['provider']=='Yahoo Finance'

def supported(asset):
    return (asset['provider']=='Kraken' and asset['currency']=='USD' and asset['kind'] in {'crypto','forex','commodity_token',*TOKEN_KINDS}) or nse_supported(asset)

def eligible(asset):
    if not supported(asset) or not asset.get('quote_fresh'):return False
    turnover=asset['price']*(asset.get('volume') or 0)
    return turnover >= (1000000 if asset['kind']=='crypto' else 10000000 if nse_supported(asset) else 100000)

def label(asset):
    if nse_supported(asset):return 'NSE public five-level book · INR · whole shares · fresh exchange time required'
    if supported(asset):return 'Kraken observed L2 · '+asset['kind'].replace('_',' ')
    return 'No executable adapter; research only'

def nse_book(symbol,getjson):
    raw_symbol=symbol.removesuffix('.NS')
    url='https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi?'+urllib.parse.urlencode(dict(functionName='getSymbolData',marketType='N',series='EQ',symbol=raw_symbol))
    requested=time.time();payload=getjson(url);fetched=time.time()
    r=payload['equityResponse'][0];meta=r['metaData'];depth=r['orderBook']
    if meta.get('symbol')!=raw_symbol or meta.get('series')!='EQ' or meta.get('marketType')!='N':raise ValueError('NSE instrument or market mismatch')
    stamp=datetime.strptime(r['lastUpdateTime'],'%d-%b-%Y %H:%M:%S').replace(tzinfo=ZoneInfo('Asia/Kolkata'))
    source_asof=stamp.timestamp();minutes=stamp.hour*60+stamp.minute
    session=stamp.weekday()<5 and 555<=minutes<930
    bids=[[float(depth['buyPrice'+str(i)]),float(depth['buyQuantity'+str(i)])] for i in range(1,6) if depth.get('buyPrice'+str(i),0)>0 and depth.get('buyQuantity'+str(i),0)>0]
    asks=[[float(depth['sellPrice'+str(i)]),float(depth['sellQuantity'+str(i)])] for i in range(1,6) if depth.get('sellPrice'+str(i),0)>0 and depth.get('sellQuantity'+str(i),0)>0]
    fresh=0<=fetched-source_asof<=120
    return dict(available=bool(session and fresh and bids and asks),symbol=symbol,adapter='NSE',requested=requested,fetched=fetched,source_asof=source_asof,source='NSE public five-level book',source_url=url,bids=bids,asks=asks,trades=[],currency='INR',decimals=0,min_qty=1,min_cost=0,price=depth.get('lastPrice'),change=meta.get('pChange',0),volume=r['tradeInfo'].get('totalTradedVolume',0),message='' if session and fresh else 'NSE session closed or exchange snapshot stale; no execution')

def evidence_allowed(asset,book,now,earliest=0):
    if asset['provider']=='Kraken':return supported(asset)
    if not nse_supported(asset) or book.get('adapter')!='NSE' or book.get('symbol')!=asset['symbol'] or book.get('currency')!='INR':return False
    asof=book.get('source_asof')
    if isinstance(asof,bool) or not isinstance(asof,(int,float)) or not math.isfinite(asof) or not earliest<=asof<=now or now-asof>120:return False
    stamp=datetime.fromtimestamp(asof,ZoneInfo('Asia/Kolkata'))
    return stamp.weekday()<5 and 555<=stamp.hour*60+stamp.minute<930

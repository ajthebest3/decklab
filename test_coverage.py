"""Isolated listing/search/currency/news checks; external responses are fixtures."""
import json,os,tempfile,time,threading,unittest,urllib.request,urllib.error
from unittest.mock import patch
TMP=tempfile.TemporaryDirectory(prefix='market-deck-coverage-tests-');os.environ['MARKET_DECK_DATA']=TMP.name
import server as m
from coverage import parse_catalog
from news_sources import parse_feed
m.init();httpd=m.ThreadingHTTPServer(('127.0.0.1',0),m.Handler);threading.Thread(target=httpd.serve_forever,daemon=True).start();BASE='http://127.0.0.1:'+str(httpd.server_port)
NSE=b'SYMBOL,NAME OF COMPANY, SERIES, ISIN NUMBER\nM&M,Mahindra & Mahindra Limited,EQ,INE101A01026\nQAINDIA,QA India Limited,EQ,INE000000000\n'
NASDAQ=b'Symbol|Security Name|Market Category|Test Issue|ETF\nQASTOCK|QA Company|Q|N|N\nQATEST|QA Test Company|Q|Y|N\nQAETF|QA Fund ETF|G|N|Y\nFile Creation Time: 20261031||||\n'
OTHER=b'ACT Symbol|Security Name|Exchange|Test Issue|ETF\nBRK.B|Berkshire Class B|N|N|N\nQAW|QA Company Warrants|A|N|N\n'
def request(path,body=None,headers=None):
 with urllib.request.urlopen(urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**(headers or {})}),timeout=10) as r:return json.load(r)
class CoverageTests(unittest.TestCase):
 def setUp(self):
  with m.db() as c:
   c.execute('DELETE FROM instrument_facts');c.execute('DELETE FROM instrument_directory');c.execute('DELETE FROM catalog_sources');c.execute("DELETE FROM assets WHERE symbol LIKE 'QA%' OR symbol IN ('M&M.NS','BRK-B')")
   c.execute('DELETE FROM news')
  m.COVERAGE.cache.clear()
 def test_nse_ampersand_inr_and_isin(self):
  records=parse_catalog(NSE.decode(),'nse');self.assertEqual(records[0]['symbol'],'M&M.NS');self.assertEqual(records[0]['currency'],'INR');self.assertEqual(records[0]['isin'],'INE101A01026')
 def test_us_test_issues_and_security_types(self):
  items=parse_catalog(NASDAQ.decode(),'nasdaq');self.assertEqual(len(items),2);self.assertEqual(items[1]['kind'],'etf')
  other=parse_catalog(OTHER.decode(),'other');self.assertEqual(other[0]['symbol'],'BRK-B');self.assertEqual(other[1]['kind'],'warrant')
 def test_import_does_not_track_or_mutate_account(self):
  with m.db() as c:before={t:m.rows(c,'SELECT * FROM '+t) for t in ['settings','orders','positions','watchlist']}
  self.assertEqual(m.COVERAGE.import_catalog('NSE equities',NSE),2)
  with m.db() as c:
   after={t:m.rows(c,'SELECT * FROM '+t) for t in before};a=c.execute("SELECT * FROM assets WHERE symbol='QAINDIA.NS'").fetchone()
  self.assertEqual(before,after);self.assertEqual(a['tracked'],0);self.assertEqual(a['currency'],'INR')
 def test_malformed_import_preserves_last_success(self):
  m.COVERAGE.import_catalog('NSE equities',NSE)
  with self.assertRaises(ValueError):m.COVERAGE.import_catalog('NSE equities',b'<html>provider error</html>')
  self.assertEqual(request('/api/catalog?q=QAINDIA')['total'],1)
 def test_catalog_pagination_region_and_search(self):
  m.COVERAGE.import_catalog('NSE equities',NSE);m.COVERAGE.import_catalog('Nasdaq listings',NASDAQ)
  result=request('/api/catalog?region=India&limit=1');self.assertGreaterEqual(result['total'],2);self.assertEqual(len(result['items']),1)
  found=request('/api/catalog?q=INE101A01026');self.assertEqual(found['items'][0]['symbol'],'M&M.NS')
  self.assertEqual(request('/api/catalog?q=Mahindra&region=US')['total'],0)
 def test_remote_search_cache_and_no_auto_tracking(self):
  response={'quotes':[{'symbol':'QAREMOTE.NS','longname':'QA Remote India','quoteType':'EQUITY','exchDisp':'NSE'}]}
  with patch.object(m.COVERAGE,'getjson',return_value=response) as mock:
   first=request('/api/catalog?q=QAREMOTE&remote=1');second=request('/api/catalog?q=QAREMOTE&remote=1')
  self.assertEqual(mock.call_count,1);self.assertEqual(first['remote'],'ok');self.assertEqual(second['items'][0]['tracked'],0);self.assertEqual(first['items'][0]['currency'],'INR')
 def test_remote_failure_keeps_local_results(self):
  m.COVERAGE.import_catalog('NSE equities',NSE)
  with patch.object(m.COVERAGE,'getjson',side_effect=OSError('offline')):found=request('/api/catalog?q=QAINDIA&remote=1')
  self.assertEqual(found['remote'],'unavailable');self.assertEqual(found['total'],1)
 def test_instrument_facts_keep_currency_time_and_no_tracking(self):
  m.COVERAGE.import_catalog('NSE equities',NSE);meta={'currency':'INR','regularMarketPrice':100,'chartPreviousClose':99,'regularMarketTime':1234,'fiftyTwoWeekHigh':150,'fiftyTwoWeekLow':80,'fullExchangeName':'NSE'}
  with patch.object(m.COVERAGE,'getjson',return_value={'chart':{'result':[{'meta':meta}]}}):result=request('/api/instrument?symbol=QAINDIA.NS')
  self.assertEqual(result['asset']['currency'],'INR');self.assertEqual(result['asset']['asof'],1234);self.assertEqual(result['asset']['tracked'],0);self.assertEqual(result['facts']['fiftyTwoWeekHigh'],150)
 def test_quote_failure_is_explicit_not_fabricated(self):
  m.COVERAGE.import_catalog('NSE equities',NSE)
  with patch.object(m.COVERAGE,'getjson',side_effect=OSError('offline')):result=request('/api/instrument?symbol=QAINDIA.NS')
  self.assertTrue(result['error']);self.assertIsNone(result['asset']['price']);self.assertFalse(result['asset']['tracked'])
 def test_failed_tracking_does_not_enable_polling(self):
  m.COVERAGE.import_catalog('NSE equities',NSE)
  with patch.object(m,'yahoo_quote',side_effect=ValueError('No provider quote')):
   with self.assertRaises(urllib.error.HTTPError):request('/api/track',{'symbol':'QAINDIA.NS'})
  with m.db() as c:self.assertEqual(c.execute("SELECT tracked FROM assets WHERE symbol='QAINDIA.NS'").fetchone()[0],0)
 def test_ampersand_tracking_accepts_real_symbol(self):
  m.COVERAGE.import_catalog('NSE equities',NSE)
  with patch.object(m,'yahoo_quote',return_value='M&M.NS'):self.assertTrue(request('/api/track',{'symbol':'M&M.NS'})['ok'])
 def test_rss_atom_and_rdf(self):
  rss=b'<rss><channel><item><title>Markets &amp; rates</title><link>https://example.com/one</link><pubDate>Fri, 30 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'
  atom=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Bank release</title><link href="https://example.com/two"/><updated>2026-10-30T12:00:00Z</updated></entry></feed>'
  rdf=b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/"><item><title>Asia</title><link>https://example.com/three</link><dc:date>2026-10-30T12:00:00Z</dc:date></item></rdf:RDF>'
  for payload in [rss,atom,rdf]:self.assertGreater(parse_feed(payload)[0]['published_ts'],0)
  with self.assertRaises(ValueError):parse_feed(b'<rss><channel/></rss>')
 def test_full_news_archive_beyond_500_and_filters(self):
  with m.db() as c:
   for i in range(550):c.execute('INSERT INTO news(id,title,url,source,published,seen,published_ts) VALUES(?,?,?,?,?,?,?)',(str(i),'India market '+str(i),'https://example.com/'+str(i),'Mint Markets' if i%2 else 'BBC World','',time.time(),i))
  allnews=request('/api/news?limit=40&page=13');self.assertEqual(allnews['total'],550);self.assertEqual(len(allnews['items']),30)
  india=request('/api/news?topic=india&q=market');self.assertEqual(india['total'],275)
 def test_host_origin_and_private_paths(self):
  with self.assertRaises(urllib.error.HTTPError) as e:request('/api/catalog',headers={'Host':'evil.example'})
  self.assertEqual(e.exception.code,403)
  for path in ['/coverage.py','/news_sources.py','/data/market.db']:
   with self.assertRaises(urllib.error.HTTPError) as e:request(path)
   self.assertEqual(e.exception.code,404)
if __name__=='__main__':
 try:unittest.main(verbosity=2)
 finally:m.STOP.set();httpd.shutdown()

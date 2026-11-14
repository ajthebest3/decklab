"""Public observer isolation: no credentials, accounts, AI or execution endpoints."""
import json,os,tempfile,threading,time,unittest,urllib.error,urllib.request
from pathlib import Path
from unittest.mock import patch
TMP=tempfile.TemporaryDirectory(prefix='decklab-observer-test-');os.environ['MARKET_DECK_DATA']=TMP.name
import observer_server as m
m.init()

class ObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http=m.core.ThreadingHTTPServer(('127.0.0.1',0),m.Handler)
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();TMP.cleanup()
    def request(self,path,body=None,host=None):
        req=urllib.request.Request('http://127.0.0.1:'+str(self.http.server_port)+path,data=json.dumps(body).encode() if body is not None else None,headers={'Host':host} if host else {})
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def test_no_financial_or_ai_tables_created(self):
        with m.core.db() as c:tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertFalse(tables&{'orders','positions','demo_orders','demo_fills','jobs','chat_messages'})
    def test_private_and_model_routes_absent(self):
        for p in ['/api/state','/api/orders','/api/ai-models','/api/admin/info','/data/market.db','/server.py']:
            self.assertEqual(self.request(p)[0],404)
    def test_all_mutations_are_rejected(self):
        for p in ['/api/orders','/api/settings','/api/research-run','/api/ai-test','/api/observer/state']:
            self.assertEqual(self.request(p,{})[0],403)
    def test_exact_host_allowlist(self):
        self.assertEqual(self.request('/api/health',host='evil.example')[0],403)
        with patch.dict(os.environ,{'CODESPACES':'true','CODESPACE_NAME':'safe-space'}):
            expected='safe-space-'+str(m.PORT)+'.app.github.dev'
            self.assertEqual(self.request('/api/health',host=expected)[0],200)
            self.assertEqual(self.request('/api/health',host='other-space-8790.app.github.dev')[0],403)
    def test_contract_hides_accounts_and_exposes_disabled_modes(self):
        code,data=self.request('/api/observer/state');self.assertEqual(code,200)
        self.assertFalse(data['ai_enabled']);self.assertFalse(data['execution_enabled'])
        self.assertNotIn('portfolio',data);self.assertNotIn('settings',data)
    def test_quote_source_and_receipt_time_are_honest(self):
        with m.core.db() as c:
            c.execute("INSERT OR IGNORE INTO assets VALUES('BTC/USD','Bitcoin','crypto','Global','USD','Kraken','XXBTZUSD',1)")
            m.core.store(c,'BTC/USD',100,1,1000,time.time(),'Kraken spot REST · receipt time, exchange time unavailable')
        data=self.request('/api/observer/state?q=BTC%2FUSD')[1];quote=data['assets'][0]
        self.assertIsNone(quote['exchange_timestamp']);self.assertEqual(quote['timestamp_basis'],'receipt-time')
    def test_watchlist_filter_is_global_parameterized_and_bounded(self):
        pins=urllib.parse.quote(json.dumps(['AAPL','MSFT']))
        data=self.request('/api/observer/state?pins='+pins)[1]
        self.assertEqual(data['total'],2)
        self.assertEqual({a['symbol'] for a in data['assets']},{'AAPL','MSFT'})
        self.assertEqual(self.request('/api/observer/state?pins=%7B%7D')[0],400)
    def test_no_model_or_order_calls_for_reads(self):
        with patch.object(m.core.MIRAI,'request',side_effect=AssertionError('AI prohibited')),patch.object(m.core,'execute_order',side_effect=AssertionError('Execution prohibited')):
            self.assertEqual(self.request('/api/observer/state')[0],200)

if __name__=='__main__':unittest.main(verbosity=2)
